import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings


_SECTION_BREAK_RE = re.compile(
    r"(?im)^\s*(sample input(?: \d+)?|sample output(?: \d+)?|explanation(?: \d+)?|input format|output format|constraints)\s*$"
)
_HACKERRANK_SECTION_HEADINGS = {
    "task": "problem_statement",
    "concept": "concept_text",
    "function description": "function_description",
    "input format": "input_format",
    "constraints": "constraints",
    "output format": "output_format",
    "sample input": "sample_input",
    "sample output": "sample_output",
    "explanation": "explanation",
    "returns": "returns",
    "parameters": "parameters",
    "code stub": "code_stub",
    "starter code": "code_stub",
}
_HACKERRANK_SECTION_HEADING_RE = re.compile(
    r"^\s*(task|concept|function description|input format|constraints|output format|"
    r"sample input(?:\s+\d+)?|sample output(?:\s+\d+)?|explanation(?:\s+\d+)?|"
    r"returns|parameters|code stub|starter code)\s*:?\s*$",
    re.IGNORECASE,
)
_HACKERRANK_UI_NOISE_RE = re.compile(
    r"^\s*(?:run code|submit code|upload code as file|line:\s*\d+|col:\s*\d+|status|difficulty|"
    r"skills|discussions|editorial|submissions|leaderboard|view discussions|view editorial)\s*$",
    re.IGNORECASE,
)
_SUSPICIOUS_IMPORT_RE = re.compile(
    r"(?im)^\s*(?:from|import)\s+(os|socket|subprocess|requests|pathlib|shutil|http|urllib|ftplib)\b"
)
_PYTHON_DEF_RE = re.compile(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*:")
_JS_FUNCTION_RE = re.compile(r"\bfunction\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
_GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
_COMPLEX_REQUIRED_METHODS = ["__init__", "__add__", "__sub__", "__mul__", "__truediv__", "mod", "__str__"]
_INPUT_VARIABLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "contain",
    "contains",
    "each",
    "element",
    "elements",
    "first",
    "followed",
    "four",
    "integer",
    "integers",
    "line",
    "lines",
    "name",
    "next",
    "nine",
    "number",
    "numbers",
    "of",
    "on",
    "one",
    "second",
    "separate",
    "separated",
    "seven",
    "six",
    "space",
    "subsequent",
    "student",
    "students",
    "ten",
    "the",
    "third",
    "three",
    "to",
    "two",
}

_LANGUAGE_PATTERNS = (
    ("typescript", r"\b(?:typescript|ts)\b"),
    ("javascript", r"\b(?:javascript|java\s*script|js)\b"),
    ("cpp", r"(?<!\w)(?:c\+\+|cpp)(?!\w)"),
    ("csharp", r"\b(?:c#|c\s+sharp)\b"),
    ("java", r"\bjava\b(?!\s*script)"),
    ("python", r"\b(?:python|py)\b"),
    ("sql", r"\bsql\b"),
)


def detect_programming_language(
    problem_text: str,
    editor_text: Optional[str] = None,
    default: str = "python",
) -> str:
    combined = "\n".join(part for part in (str(problem_text or ""), str(editor_text or "")) if part)
    normalized = combined.lower()
    for language, pattern in _LANGUAGE_PATTERNS:
        if re.search(pattern, normalized):
            return language
    if re.search(r"\bclass\s+Solution\b.*\bpublic\b|\bpublic\s+static\b", combined, re.IGNORECASE | re.DOTALL):
        return "java"
    if _JS_FUNCTION_RE.search(combined):
        return "javascript"
    if _PYTHON_DEF_RE.search(combined) or re.search(r"\binput\(\)|\bprint\(", combined):
        return "python"
    return default


def clean_extracted_problem_text(text: str) -> str:
    """Remove analyzer/debug noise while preserving real problem sections."""
    diagnostic_key_pattern = re.compile(
        r"^\s*(?:"
        r"INFO:|DEBUG:|WARNING:|ERROR:|"
        r"coding runtime audit\b|answer generation completed\b|"
        r"request_question_excerpt\b|full_problem_text_present\b|full_problem_text_excerpt\b|"
        r"generate_full_problem_text_len\b|generate_editor_text_len\b|editor_text_present\b|"
        r"input_format_used\b|output_format_used\b|sample_tests_found\b|"
        r"hackerrank_context_ready\b|missing_context_sections\b|"
        r"full_problem_text_is_summary_only\b|full_problem_text_contains_json_noise\b|"
        r"submission_ready_code\b|code_validation_passed\b|raw_vision_json\b"
        r")",
        re.IGNORECASE,
    )
    ui_noise_pattern = re.compile(
        r"^\s*(?:Run Code|Submit Code|Upload Code as File|Line:|Col:|Status|"
        r"Difficulty|Skills|Discussions|Editorial)\s*$",
        re.IGNORECASE,
    )

    lines: list[str] = []
    for line in str(text or "").replace("\r\n", "\n").splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and (
            '"is_question"' in stripped
            or "'is_question'" in stripped
            or '"question_type"' in stripped
            or "'question_type'" in stripped
            or '"raw_vision_json"' in stripped
        ):
            continue
        if diagnostic_key_pattern.search(stripped) or ui_noise_pattern.search(stripped):
            continue
        cleaned = re.sub(r"\s*\{\s*['\"]is_question['\"]\s*:.*$", "", line).rstrip()
        cleaned = re.sub(r"\s*\{[^{}]*['\"]question_type['\"]\s*:\s*['\"]coding['\"].*$", "", cleaned).rstrip()
        if cleaned.strip():
            lines.append(cleaned)
    return "\n".join(lines).strip()


def contains_extracted_problem_json_noise(value: str) -> bool:
    text = str(value or "")
    return bool(
        re.search(r"\{\s*['\"]is_question['\"]\s*:", text)
        or re.search(r"['\"]question_type['\"]\s*:\s*['\"]coding['\"]", text)
        or re.search(r"['\"]raw_vision_json['\"]\s*:", text)
    )


def evaluate_hackerrank_context_readiness(
    *,
    platform: str,
    coding_answer_mode: bool,
    problem_text: str,
    input_format: str,
    output_format: str,
    sample_input: str,
    sample_output: str,
    sample_tests_found: int,
) -> dict:
    is_hackerrank = str(platform or "").strip().lower() == "hackerrank" or "hackerrank" in str(problem_text or "").lower()
    clean_problem_text = clean_extracted_problem_text(problem_text)
    if not (is_hackerrank and coding_answer_mode):
        return {
            "hackerrank_context_ready": None,
            "missing_context_sections": [],
            "full_problem_text_is_summary_only": False,
            "full_problem_text_contains_json_noise": contains_extracted_problem_json_noise(problem_text),
            "clean_full_problem_text_len": len(clean_problem_text),
            "context_readiness_hard_block_applied": False,
            "submission_ready_block_reason": "",
        }

    text = clean_problem_text
    normalized = text.lower()
    has_problem_statement = bool(
        re.search(r"\b(task|problem statement|description|function description)\b", normalized)
        or (len(text.strip()) >= 300 and "input format" in normalized and "output format" in normalized)
    )
    has_input_format = bool(str(input_format or "").strip() or "input format" in normalized)
    has_output_format = bool(str(output_format or "").strip() or "output format" in normalized)
    has_sample_input = bool(str(sample_input or "").strip() or "sample input" in normalized or sample_tests_found > 0)
    has_sample_output = bool(str(sample_output or "").strip() or "sample output" in normalized or sample_tests_found > 0)
    full_problem_text_contains_json_noise = contains_extracted_problem_json_noise(problem_text)
    full_problem_text_is_summary_only = bool(
        not has_input_format
        and not has_output_format
        and not has_sample_input
        and not has_sample_output
    )

    missing_context_sections: list[str] = []
    if not has_problem_statement or full_problem_text_is_summary_only:
        missing_context_sections.append("problem_statement")
    if not has_input_format:
        missing_context_sections.append("input_format")
    if not has_output_format:
        missing_context_sections.append("output_format")
    if not has_sample_input:
        missing_context_sections.append("sample_input")
    if not has_sample_output:
        missing_context_sections.append("sample_output")
    if full_problem_text_contains_json_noise:
        missing_context_sections.append("clean_full_problem_text")

    return {
        "hackerrank_context_ready": not missing_context_sections,
        "missing_context_sections": missing_context_sections,
        "full_problem_text_is_summary_only": full_problem_text_is_summary_only,
        "full_problem_text_contains_json_noise": full_problem_text_contains_json_noise,
        "clean_full_problem_text_len": len(clean_problem_text),
        "context_readiness_hard_block_applied": False,
        "submission_ready_block_reason": "",
    }


def force_context_not_ready_for_json_noise(context_status: dict, json_noise_detected: bool) -> dict:
    if not json_noise_detected or context_status.get("hackerrank_context_ready") is None:
        return context_status
    missing = list(context_status.get("missing_context_sections") or [])
    if "clean_full_problem_text" not in missing:
        missing.append("clean_full_problem_text")
    context_status["full_problem_text_contains_json_noise"] = True
    context_status["missing_context_sections"] = missing
    context_status["hackerrank_context_ready"] = False
    return context_status


def apply_hackerrank_context_gate(result: Dict[str, Any], context_status: dict) -> Dict[str, Any]:
    if context_status.get("hackerrank_context_ready") is not False:
        result.update(context_status)
        result["context_readiness_hard_block_applied"] = False
        result["submission_ready_block_reason"] = ""
        return result

    reason = "Full HackerRank problem context was not captured."
    warning = "Full HackerRank problem context was not captured."
    errors = list(result.get("code_validation_errors") or [])
    if reason not in errors:
        errors.append(reason)
    result["submission_ready_code"] = False
    result["code_validation_passed"] = False
    result["code_validation_errors"] = errors
    result["correction_pass_needed"] = False
    result["correction_pass_used"] = False
    result["correction_skip_reason"] = "context_not_ready"
    result["unverified_code_warning"] = warning
    result.update(context_status)
    result["context_readiness_hard_block_applied"] = True
    result["submission_ready_block_reason"] = reason
    return result

_TRUNCATED_OPERATOR_RE = re.compile(r"(?:=|\+|-|\*|/|%|//)\s*$")
_BARE_IDENTIFIER_LIST_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)+$"
)
_EDITOR_PLACEHOLDER_RE = re.compile(
    r"(complete|return a list|write your code|your code goes here|todo|notimplemented|not implemented|pass\b|^\s*\.\.\.\s*$)",
    re.IGNORECASE,
)
_GENERIC_STDIN_EDITOR_RE = re.compile(
    r"enter your code here|read input from stdin|print output to stdout",
    re.IGNORECASE,
)
_EDITOR_UI_NOISE_RE = re.compile(
    r"exit full screen view|change theme|language\s+python|line:\s*\d+|col:\s*\d+|"
    r"upload\s+codeasfile|runcode|submitcode|test against custom input|problem solving|hackerrank",
    re.IGNORECASE,
)
_MEANINGFUL_EDITOR_IMPORT_RE = re.compile(r"^\s*(?:from\s+\S+\s+import\s+.+|import\s+.+)$")
_MEANINGFUL_EDITOR_ASSIGNMENT_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?!input\s*\(|print\s*\().+"
)
_MEANINGFUL_EDITOR_DECORATOR_RE = re.compile(r"^\s*@[A-Za-z_][A-Za-z0-9_.()]*")
_MEANINGFUL_EDITOR_CONTROL_RE = re.compile(r"^\s*(?:if|for|while|try|with)\b.+:\s*$")


def _last_non_empty_line(code: str) -> str:
    for line in reversed(str(code or "").splitlines()):
        if line.strip():
            return line.rstrip()
    return ""


def _has_unmatched_delimiters(code: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {value: key for key, value in pairs.items()}
    stack: list[str] = []
    in_single = False
    in_double = False
    escape = False

    for char in str(code or ""):
        if escape:
            escape = False
            continue
        if char == "\\" and (in_single or in_double):
            escape = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if in_single or in_double:
            continue
        if char in pairs:
            stack.append(char)
        elif char in closing:
            if not stack or stack[-1] != closing[char]:
                return True
            stack.pop()

    return bool(stack) or in_single or in_double


def validate_python_code_completeness(code: str) -> dict:
    code_text = str(code or "")
    errors: list[str] = []
    last_line = _last_non_empty_line(code_text).strip()
    last_line_lower = last_line.lower()

    if not code_text.strip():
        errors.append("Python code is empty.")
    if last_line.endswith(","):
        errors.append("Last non-empty line ends with a trailing comma.")
    if last_line and _TRUNCATED_OPERATOR_RE.search(last_line):
        errors.append("Last non-empty line ends with an unfinished operator or assignment.")
    if last_line and _BARE_IDENTIFIER_LIST_RE.fullmatch(last_line):
        errors.append("Last non-empty line is a bare comma-separated identifier list, which looks truncated.")
    if last_line.startswith("#") and "read input" in last_line_lower:
        errors.append("Code ends with a dangling input comment and no runnable input handling.")
    if _has_unmatched_delimiters(code_text):
        errors.append("Python code has unmatched parentheses, brackets, braces, or quotes.")

    try:
        ast.parse(code_text)
        python_syntax_valid = True
    except SyntaxError as exc:
        python_syntax_valid = False
        errors.insert(0, f"Python syntax validation failed: {exc.msg} (line {exc.lineno}, column {exc.offset})")

    return {
        "passed": python_syntax_valid and not errors,
        "errors": errors,
        "python_syntax_valid": python_syntax_valid,
        "incomplete_code_detected": bool(errors),
    }


def _split_python_code_and_comment(line: str) -> tuple[str, str]:
    in_single = False
    in_double = False
    escape = False
    for index, char in enumerate(line):
        if escape:
            escape = False
            continue
        if char == "\\" and (in_single or in_double):
            escape = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return line[:index].rstrip(), line[index:].strip()
    return line.rstrip(), ""


def build_editor_stub_contract(editor_text: str, selected_language: Optional[str] = "python") -> dict:
    stub_text = str(editor_text or "").replace("\r\n", "\n").strip("\n")
    language = str(selected_language or "python").strip().lower() or "python"
    real_code_lines: list[str] = []
    comment_lines: list[str] = []
    placeholder_lines: list[str] = []
    required_functions: list[str] = []
    required_lambdas: list[str] = []
    required_classes: list[str] = []
    required_import_lines: list[str] = []
    required_assignment_lines: list[str] = []
    required_assignment_targets: list[str] = []
    required_decorator_lines: list[str] = []
    meaningful_structural_lines: list[str] = []
    runner_detected = False
    ui_noise_hits: list[str] = []

    for raw_line in stub_text.splitlines():
        if not raw_line.strip():
            continue
        if _EDITOR_UI_NOISE_RE.search(raw_line.strip()):
            ui_noise_hits.append(raw_line.strip())
            continue
        code_part, comment_part = _split_python_code_and_comment(raw_line)
        stripped_code = code_part.strip()
        stripped_comment = comment_part.strip()

        if stripped_comment:
            comment_lines.append(stripped_comment)
            if _EDITOR_PLACEHOLDER_RE.search(stripped_comment):
                placeholder_lines.append(stripped_comment)
        if stripped_code:
            real_code_lines.append(code_part.rstrip())
            if _EDITOR_PLACEHOLDER_RE.search(stripped_code):
                placeholder_lines.append(stripped_code)
            if _MEANINGFUL_EDITOR_IMPORT_RE.match(code_part):
                required_import_lines.append(stripped_code)
                meaningful_structural_lines.append(stripped_code)
            if _MEANINGFUL_EDITOR_DECORATOR_RE.match(code_part):
                required_decorator_lines.append(stripped_code)
                meaningful_structural_lines.append(stripped_code)
            assignment_match = _MEANINGFUL_EDITOR_ASSIGNMENT_RE.match(code_part)
            if assignment_match:
                required_assignment_lines.append(stripped_code)
                meaningful_structural_lines.append(stripped_code)
                assignment_target = assignment_match.group(1)
                if assignment_target not in required_assignment_targets:
                    required_assignment_targets.append(assignment_target)
            elif _MEANINGFUL_EDITOR_CONTROL_RE.match(code_part):
                meaningful_structural_lines.append(stripped_code)

        lambda_match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*lambda\b", code_part)
        if lambda_match and lambda_match.group(1) not in required_lambdas:
            required_lambdas.append(lambda_match.group(1))
        function_match = re.match(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code_part)
        if function_match and function_match.group(1) not in required_functions:
            required_functions.append(function_match.group(1))
        class_match = re.match(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b", code_part)
        if class_match and class_match.group(1) not in required_classes:
            required_classes.append(class_match.group(1))
        if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", code_part):
            runner_detected = True

    required_symbols = required_lambdas + required_functions + required_classes
    effective_placeholder_lines = list(placeholder_lines)
    if (
        runner_detected
        and not required_symbols
        and not required_assignment_targets
        and not required_decorator_lines
        and effective_placeholder_lines
        and all(re.fullmatch(r"\s*pass\b\s*", line) for line in effective_placeholder_lines)
    ):
        effective_placeholder_lines = []
    import_only_structure = bool(
        required_import_lines
        and not required_symbols
        and not required_assignment_targets
        and not required_decorator_lines
        and not effective_placeholder_lines
    )
    runner_only_structure = bool(
        runner_detected
        and not required_symbols
        and not required_assignment_targets
        and not required_decorator_lines
        and not effective_placeholder_lines
    )
    has_real_stub = bool(
        required_symbols
        or required_assignment_targets
        or required_decorator_lines
        or (
            effective_placeholder_lines
            and (
                required_symbols
                or required_assignment_targets
                or required_decorator_lines
            )
        )
        or (
            meaningful_structural_lines
            and not import_only_structure
            and not runner_only_structure
        )
    )
    generic_stdin_only = bool(
        stub_text.strip()
        and not has_real_stub
        and (
            all(
                (not _split_python_code_and_comment(line)[0].strip())
                and (
                    not _split_python_code_and_comment(line)[1].strip()
                    or _GENERIC_STDIN_EDITOR_RE.search(_split_python_code_and_comment(line)[1])
                )
                for line in stub_text.splitlines()
                if line.strip()
            )
            or bool(ui_noise_hits)
            or import_only_structure
            or runner_only_structure
        )
    )
    editor_stub_mode = "editor_stub_completion" if has_real_stub else ("generic_stdin" if generic_stdin_only else "none")
    return {
        "editor_stub_used": editor_stub_mode == "editor_stub_completion",
        "stub_language": language,
        "stub_code": stub_text,
        "real_code_lines": real_code_lines,
        "comment_lines": comment_lines,
        "placeholder_lines": effective_placeholder_lines,
        "required_symbols": required_symbols,
        "required_functions": required_functions,
        "required_lambdas": required_lambdas,
        "required_classes": required_classes,
        "required_import_lines": required_import_lines,
        "required_assignment_lines": required_assignment_lines,
        "required_assignment_targets": required_assignment_targets,
        "required_decorator_lines": required_decorator_lines,
        "meaningful_structural_lines": meaningful_structural_lines,
        "ui_noise_hits": ui_noise_hits,
        "must_preserve_runner": runner_detected,
        "editor_runner_detected": runner_detected,
        "editor_stub_mode": editor_stub_mode,
        "code_generation_mode": "editor_stub_completion" if has_real_stub else "stdin_full_solution",
    }


def validate_editor_stub_completion(code: str, editor_stub_contract: dict) -> dict:
    contract = editor_stub_contract or {}
    if not contract.get("editor_stub_used"):
        return {
            "passed": True,
            "errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": True,
            "editor_stub_validation_errors": [],
        }
    if str(contract.get("stub_language") or "python").lower() != "python":
        return {
            "passed": True,
            "errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": None,
            "editor_stub_validation_errors": [],
            "editor_stub_validation_scope": "hackerrank_python_only",
        }

    code_text = str(code or "")
    errors: list[str] = []
    syntax_validation = validate_python_code_completeness(code_text)
    if not syntax_validation["passed"]:
        errors.extend(syntax_validation["errors"])

    required_lambdas = [str(name) for name in contract.get("required_lambdas") or []]
    required_functions = [str(name) for name in contract.get("required_functions") or []]
    required_classes = [str(name) for name in contract.get("required_classes") or []]
    required_symbols = [str(name) for name in contract.get("required_symbols") or []]
    required_import_lines = [str(line) for line in contract.get("required_import_lines") or []]
    required_assignment_targets = [str(name) for name in contract.get("required_assignment_targets") or []]
    required_decorator_lines = [str(line) for line in contract.get("required_decorator_lines") or []]

    missing_lambdas = [
        name for name in required_lambdas
        if not re.search(rf"(?m)^[ \t]*{re.escape(name)}\s*=\s*lambda\b.+", code_text)
    ]
    missing_functions = [
        name for name in required_functions
        if not re.search(rf"(?m)^[ \t]*def\s+{re.escape(name)}\s*\(", code_text)
    ]
    missing_classes = [
        name for name in required_classes
        if not re.search(rf"(?m)^[ \t]*class\s+{re.escape(name)}\b", code_text)
    ]

    if missing_lambdas:
        errors.append(f"Editor starter code requires lambda(s): {', '.join(missing_lambdas)}.")
    if missing_functions:
        errors.append(f"Editor starter code requires function(s): {', '.join(missing_functions)}.")
    if missing_classes:
        errors.append(f"Editor starter code requires class(es): {', '.join(missing_classes)}.")
    missing_imports = [
        line for line in required_import_lines
        if line and line not in code_text
    ]
    if missing_imports:
        errors.append(
            "Editor starter code requires preserving import/setup line(s): "
            + ", ".join(missing_imports)
            + "."
        )
    missing_assignment_targets = [
        name for name in required_assignment_targets
        if not re.search(rf"(?m)^[ \t]*{re.escape(name)}\s*=", code_text)
    ]
    if missing_assignment_targets:
        errors.append(
            "Editor starter code requires preserving assignment/setup symbol(s): "
            + ", ".join(missing_assignment_targets)
            + "."
        )
    missing_decorators = [
        line for line in required_decorator_lines
        if line and line not in code_text
    ]
    if missing_decorators:
        errors.append(
            "Editor starter code requires preserving decorator line(s): "
            + ", ".join(missing_decorators)
            + "."
        )
    if contract.get("must_preserve_runner") and not re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", code_text):
        errors.append("Editor starter code requires preserving the __main__ runner block.")

    missing_symbols = missing_lambdas + missing_functions + missing_classes
    if missing_symbols:
        errors.append(
            f"Editor starter code requires completing required symbol(s): {', '.join(missing_symbols)}."
        )

    for name in required_functions:
        if len(re.findall(rf"(?m)^[ \t]*def\s+{re.escape(name)}\s*\(", code_text)) > 1:
            errors.append(f"Duplicate required function definition detected: {name}.")
    for name in required_classes:
        if len(re.findall(rf"(?m)^[ \t]*class\s+{re.escape(name)}\b", code_text)) > 1:
            errors.append(f"Duplicate required class definition detected: {name}.")

    placeholder_hits = [
        line.strip()
        for line in code_text.splitlines()
        if _EDITOR_PLACEHOLDER_RE.search(line)
    ]
    if placeholder_hits:
        errors.append("Editor starter code placeholders must be replaced with working code.")

    has_standalone_io = bool(re.search(r"\binput\s*\(", code_text) and re.search(r"\bprint\s*\(", code_text))
    if has_standalone_io and required_symbols and missing_symbols:
        errors.append(
            "Generated code ignored the HackerRank editor starter code; standalone solution rejected."
        )

    return {
        "passed": not errors,
        "errors": errors,
        "editor_stub_validation_used": True,
        "editor_stub_validation_passed": not errors,
        "editor_stub_validation_errors": errors,
        "editor_stub_validation_scope": "hackerrank_python",
    }


def _section_between(text: str, start_label: str, next_labels: tuple[str, ...]) -> str:
    normalized = text.lower()
    start = normalized.find(start_label.lower())
    if start == -1:
        return ""
    start += len(start_label)
    end = len(text)
    for label in next_labels:
        idx = normalized.find(label.lower(), start)
        if idx != -1 and idx < end:
            end = idx
    return text[start:end].strip()


def _canonical_hackerrank_heading(label: str) -> str:
    normalized = re.sub(r"\s+\d+$", "", str(label or "").strip().lower())
    return _HACKERRANK_SECTION_HEADINGS.get(normalized, normalized.replace(" ", "_"))


def _clean_hackerrank_problem_lines(problem_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(problem_text or "").replace("\r\n", "\n").splitlines():
        line = raw_line.rstrip()
        if _HACKERRANK_UI_NOISE_RE.fullmatch(line.strip()):
            continue
        lines.append(line)
    return lines


def _extract_hackerrank_sections(problem_text: str) -> dict:
    lines = _clean_hackerrank_problem_lines(problem_text)
    intro_lines: list[str] = []
    sections: dict[str, str] = {}
    sample_tests: list[dict[str, str]] = []
    active_key: Optional[str] = None
    active_sample_index: Optional[int] = None

    for line in lines:
        heading_match = _HACKERRANK_SECTION_HEADING_RE.match(line.strip())
        if heading_match:
            raw_heading = heading_match.group(1).strip()
            active_key = _canonical_hackerrank_heading(raw_heading)
            sample_match = re.search(r"\b(sample input|sample output)(?:\s+(\d+))?\b", raw_heading, re.IGNORECASE)
            if sample_match:
                active_sample_index = int(sample_match.group(2) or len(sample_tests))
                while len(sample_tests) <= active_sample_index:
                    sample_tests.append({"input": "", "expected_output": ""})
            else:
                active_sample_index = None
            sections.setdefault(active_key, "")
            continue

        if active_key is None:
            intro_lines.append(line)
            continue

        existing = sections.get(active_key, "")
        sections[active_key] = f"{existing}\n{line}".strip("\n")
        if active_key == "sample_input" and active_sample_index is not None:
            current = sample_tests[active_sample_index].get("input", "")
            sample_tests[active_sample_index]["input"] = f"{current}\n{line}".strip("\n")
        elif active_key == "sample_output" and active_sample_index is not None:
            current = sample_tests[active_sample_index].get("expected_output", "")
            sample_tests[active_sample_index]["expected_output"] = f"{current}\n{line}".strip("\n")

    meaningful_intro = [
        line.strip()
        for line in intro_lines
        if line.strip() and line.strip().lower() not in {"hackerrank", "python", "problem solving"}
    ]
    problem_title = meaningful_intro[0] if meaningful_intro else ""
    intro_body = "\n".join(meaningful_intro[1:] if problem_title else meaningful_intro).strip()
    if sections.get("problem_statement"):
        problem_statement = sections["problem_statement"].strip()
        if intro_body:
            problem_statement = f"{intro_body}\n\n{problem_statement}".strip()
    else:
        problem_statement = intro_body

    return {
        "problem_title": problem_title,
        "problem_statement": problem_statement,
        "concept_text": sections.get("concept_text", "").strip(),
        "function_description": sections.get("function_description", "").strip(),
        "input_format": sections.get("input_format", "").strip(),
        "constraints": sections.get("constraints", "").strip(),
        "output_format": sections.get("output_format", "").strip(),
        "sample_tests": [
            {
                "input": str(sample.get("input", "")).strip(),
                "expected_output": str(sample.get("expected_output", "")).strip(),
            }
            for sample in sample_tests
            if str(sample.get("input", "")).strip() or str(sample.get("expected_output", "")).strip()
        ],
        "explanation": sections.get("explanation", "").strip(),
        "returns": sections.get("returns", "").strip(),
        "parameters": sections.get("parameters", "").strip(),
        "code_stub": sections.get("code_stub", "").strip(),
        "sections_found": {
            "problem_statement": bool(problem_statement),
            "concept": bool(sections.get("concept_text")),
            "input_format": bool(sections.get("input_format")),
            "output_format": bool(sections.get("output_format")),
            "constraints": bool(sections.get("constraints")),
            "sample_input": any(str(sample.get("input", "")).strip() for sample in sample_tests),
            "sample_output": any(str(sample.get("expected_output", "")).strip() for sample in sample_tests),
        },
    }


def build_hackerrank_problem_contract(
    problem_text: str,
    editor_text: Optional[str] = None,
    platform_title: Optional[str] = None,
    selected_language: Optional[str] = None,
) -> dict:
    sections = _extract_hackerrank_sections(problem_text)
    base_contract = build_coding_input_contract(problem_text, editor_text)
    editor_stub = str(editor_text or sections.get("code_stub") or "").strip()
    editor_stub_contract = build_editor_stub_contract(editor_stub, selected_language)
    if editor_stub and not editor_text:
        base_contract = build_coding_input_contract(problem_text, editor_stub)

    sample_tests = sections.get("sample_tests") or base_contract.get("sample_tests") or extract_sample_tests(problem_text)
    mode = str(base_contract.get("code_generation_mode") or base_contract.get("mode") or "unknown")
    if editor_stub_contract.get("editor_stub_used"):
        mode = "editor_stub_completion"
    elif base_contract.get("class_stub_detected"):
        mode = "class_stub"
    elif base_contract.get("function_stub_detected"):
        mode = "function_stub"

    stub_rules = {
        "has_stub": bool(
            editor_stub_contract.get("editor_stub_used")
            or base_contract.get("function_stub_detected")
            or base_contract.get("class_stub_detected")
        ),
        "function_name": base_contract.get("function_name"),
        "function_params": base_contract.get("function_params") or [],
        "class_name": base_contract.get("class_name"),
        "required_methods": base_contract.get("required_methods") or [],
        "required_symbols": editor_stub_contract.get("required_symbols") or [],
        "required_functions": editor_stub_contract.get("required_functions") or [],
        "required_lambdas": editor_stub_contract.get("required_lambdas") or [],
        "required_classes": editor_stub_contract.get("required_classes") or [],
        "required_import_lines": editor_stub_contract.get("required_import_lines") or [],
        "required_assignment_targets": editor_stub_contract.get("required_assignment_targets") or [],
        "required_decorator_lines": editor_stub_contract.get("required_decorator_lines") or [],
        "must_preserve_stub": bool(editor_stub or base_contract.get("function_stub_detected") or base_contract.get("class_stub_detected")),
        "must_preserve_runner": bool(editor_stub_contract.get("must_preserve_runner")),
        "should_generate_standalone_io": mode == "stdin_full_solution",
    }
    concept_rules: list[str] = []
    if sections.get("concept_text"):
        concept_rules.append("Use the Concept section when choosing the algorithm or required language feature.")
    if base_contract.get("problem_family") == "complex_numbers_class":
        concept_rules.extend(
            [
                "Implement the custom Complex class and overload the required operators.",
                "Do not solve the problem using only Python's built-in complex type.",
                "Format complex values with two decimal places and i suffix.",
            ]
        )

    validation_requirements = [
        "Follow Input Format exactly.",
        "Follow Output Format exactly.",
        "Use Sample Input and Sample Output only for validation, not hardcoding.",
        "Preserve visible function/class stub requirements.",
        "Return one complete Python code block.",
    ]
    if sample_tests:
        validation_requirements.append("Generated Python code must pass the extracted sample tests.")
    if base_contract.get("skip_count_prefix"):
        validation_requirements.append("Skip Ni/count prefixes using the parsed line values after index 0.")
    if base_contract.get("count_value_pairs"):
        validation_requirements.append("Read count lines as metadata before reading each value line.")
    if base_contract.get("output_requires_sorting"):
        validation_requirements.append("Sort selected output values as required before printing.")

    contract = {
        **base_contract,
        "platform": "hackerrank",
        "platform_detected": "hackerrank",
        "platform_adapter": "hackerrank_python",
        "hackerrank_contract_used": True,
        "hackerrank_full_problem_used": bool(
            sections.get("input_format")
            and sections.get("output_format")
            and (sections.get("sample_tests") or sections.get("problem_statement"))
        ),
        "hackerrank_subdomain": None,
        "language": "python" if str(selected_language or "").lower() in {"", "python"} else str(selected_language),
        "problem_title": sections.get("problem_title") or str(platform_title or "").strip(),
        "problem_statement": sections.get("problem_statement", ""),
        "concept_text": sections.get("concept_text", ""),
        "function_description": sections.get("function_description", ""),
        "input_format": sections.get("input_format", ""),
        "constraints": sections.get("constraints", ""),
        "output_format": sections.get("output_format", ""),
        "sample_tests": sample_tests,
        "sample_tests_source": "hackerrank_sections" if sections.get("sample_tests") else base_contract.get("sample_tests_source", "none"),
        "explanation": sections.get("explanation", ""),
        "returns": sections.get("returns", ""),
        "parameters": sections.get("parameters", ""),
        "editor_stub": editor_stub,
        "editor_stub_contract": editor_stub_contract,
        "editor_stub_used": bool(editor_stub_contract.get("editor_stub_used")),
        "editor_stub_mode": editor_stub_contract.get("editor_stub_mode"),
        "editor_required_symbols": editor_stub_contract.get("required_symbols") or [],
        "editor_required_functions": editor_stub_contract.get("required_functions") or [],
        "editor_required_lambdas": editor_stub_contract.get("required_lambdas") or [],
        "editor_required_classes": editor_stub_contract.get("required_classes") or [],
        "editor_required_import_lines": editor_stub_contract.get("required_import_lines") or [],
        "editor_required_assignment_targets": editor_stub_contract.get("required_assignment_targets") or [],
        "editor_required_decorator_lines": editor_stub_contract.get("required_decorator_lines") or [],
        "editor_runner_detected": bool(editor_stub_contract.get("editor_runner_detected")),
        "editor_placeholder_lines": editor_stub_contract.get("placeholder_lines") or [],
        "mode": mode,
        "code_generation_mode": mode,
        "stub_rules": stub_rules,
        "concept_rules": concept_rules,
        "validation_requirements": validation_requirements,
        "output_rules": [
            rule for rule in (
                sections.get("output_format", ""),
                "Sort output alphabetically." if base_contract.get("output_sort_order") == "alphabetical" else "",
                "Print each selected item on its own line." if base_contract.get("output_items_per_line") else "",
            )
            if rule
        ],
        "contract_sections_found": {
            **sections.get("sections_found", {}),
            "editor_stub": bool(editor_stub),
        },
    }
    return contract


def extract_input_variables(fragment: str) -> list[str]:
    text = str(fragment or "").strip()
    if not text:
        return []

    candidate = text
    candidate = re.sub(r",\s*(?:the\s+)?(?:name|number)\b.*$", "", candidate, flags=re.IGNORECASE)
    type_match = re.search(
        r"\bintegers?\s+(.+?)(?:,\s*each\b|\s+each\b|\s+on\s+a\s+separate\s+line\b|\.|$)",
        text,
        re.IGNORECASE,
    )
    if type_match:
        candidate = type_match.group(1)
    else:
        contains_match = re.search(
            r"\bcontains?\s+(.+?)(?:,\s*the\b|,\s*a\b|\.|$)",
            text,
            re.IGNORECASE,
        )
        if contains_match:
            candidate = contains_match.group(1)

    cleaned = re.sub(r"[^A-Za-z0-9_]+", " ", candidate)
    variables: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", cleaned):
        if token.lower() in _INPUT_VARIABLE_STOPWORDS:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        variables.append(token)
    return variables


def _empty_llm_contract(*, used: bool = False, error: str = "") -> dict:
    return {
        "llm_contract_used": used,
        "llm_contract_error": error,
        "platform": "generic",
        "language": "unknown",
        "mode": "unknown",
        "problem_family": "generic",
        "task_summary": "",
        "input_steps": [],
        "output_rules": [],
        "ordering_rules": [],
        "stub_rules": {
            "has_stub": False,
            "function_name": None,
            "must_preserve_stub": False,
            "should_generate_standalone_io": True,
        },
        "sample_tests": [],
        "critical_constraints": [],
    }


def _coerce_llm_contract(payload: Any, *, used: bool = True, error: str = "") -> dict:
    contract = _empty_llm_contract(used=used, error=error)
    if not isinstance(payload, dict):
        return contract

    for key in (
        "platform",
        "language",
        "mode",
        "problem_family",
        "task_summary",
        "input_steps",
        "output_rules",
        "ordering_rules",
        "stub_rules",
        "sample_tests",
        "critical_constraints",
    ):
        if key in payload:
            contract[key] = payload[key]

    if not isinstance(contract.get("input_steps"), list):
        contract["input_steps"] = []
    if not isinstance(contract.get("output_rules"), list):
        contract["output_rules"] = []
    if not isinstance(contract.get("ordering_rules"), list):
        contract["ordering_rules"] = []
    if not isinstance(contract.get("sample_tests"), list):
        contract["sample_tests"] = []
    if not isinstance(contract.get("critical_constraints"), list):
        contract["critical_constraints"] = []
    if not isinstance(contract.get("stub_rules"), dict):
        contract["stub_rules"] = _empty_llm_contract()["stub_rules"]
    return contract


def _extract_json_payload(text: str) -> dict:
    content = str(text or "").strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def extract_structured_coding_contract_with_llm(
    problem_text: str,
    editor_text: Optional[str] = None,
    platform_title: Optional[str] = None,
    selected_language: Optional[str] = None,
) -> dict:
    """Ask the existing Groq-compatible provider for a judge contract, not a solution."""
    api_key = str(getattr(settings, "GROQ_API_KEY", "") or "").strip()
    if not api_key:
        return _empty_llm_contract(used=False, error="groq_api_key_missing")

    model = (
        str(getattr(settings, "REFINEMENT_GROQ_MODEL", "") or "").strip()
        or str(getattr(settings, "GROQ_MODEL", "") or "").strip()
        or str(getattr(settings, "PRIMARY_GROQ_MODEL", "") or "").strip()
    )
    if not model:
        return _empty_llm_contract(used=False, error="groq_model_missing")

    timeout_ms = int(getattr(settings, "REFINEMENT_TIMEOUT_MS", 12000) or 12000)
    timeout_seconds = max(3.0, min(timeout_ms / 1000, 20.0))
    schema = {
        "platform": "hackerrank|leetcode|codeforces|codechef|atcoder|gfg|generic",
        "language": "python|cpp|java|javascript|sql|unknown",
        "mode": "stdin_full_solution|function_stub|leetcode_class|driver_code|unknown",
        "problem_family": "set_difference|nested_lists|maximize_it|list_comprehensions|finding_percentage|leap_year|generic",
        "task_summary": "short summary",
        "input_steps": [
            {
                "step": 1,
                "description": "read integer n",
                "variable_names": ["n"],
                "source": "stdin",
                "line_type": "single_integer|space_separated_values|count_then_values|raw_string|unknown",
                "ignore_or_skip": False,
            }
        ],
        "output_rules": ["print total count as a single integer"],
        "ordering_rules": ["sort names alphabetically before printing"],
        "stub_rules": {
            "has_stub": False,
            "function_name": None,
            "must_preserve_stub": False,
            "should_generate_standalone_io": True,
        },
        "sample_tests": [{"input": "sample input text", "expected_output": "sample output text"}],
        "critical_constraints": ["do not ignore count lines"],
    }
    prompt = (
        "Extract a structured coding judge contract from the full problem. Do not solve it.\n"
        "Read the full Input Format and Output Format carefully.\n"
        "Only describe how code must read input, produce output, and respect platform format.\n"
        "Detect count lines that are only metadata, separate-line variables, function stubs, class Solution, "
        "output ordering requirements, and sample tests exactly if present.\n"
        "Return strict JSON only, with this schema shape:\n"
        f"{json.dumps(schema, ensure_ascii=True)}\n\n"
        f"Platform/title: {platform_title or ''}\n"
        f"Selected language: {selected_language or ''}\n\n"
        f"Visible editor/stub:\n{editor_text or ''}\n\n"
        f"Problem text:\n{problem_text or ''}"
    )

    try:
        request_body = json.dumps(
            {
                "model": model,
                "temperature": 0,
                "max_tokens": 900,
                "messages": [
                    {
                        "role": "system",
                        "content": "You extract online judge coding contracts. Return JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _GROQ_CHAT_COMPLETIONS_URL,
            data=request_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return _coerce_llm_contract(_extract_json_payload(content), used=True)
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        error_name = exc.__class__.__name__
        return _empty_llm_contract(used=False, error=f"llm_contract_failed:{error_name}")


def detect_code_generation_mode(problem_text: str, editor_text: Optional[str] = None) -> dict:
    problem = str(problem_text or "")
    editor = str(editor_text or "")
    combined = "\n".join(part for part in (problem, editor) if part).strip()
    normalized = combined.lower()
    language = detect_programming_language(problem, editor, default="python")

    platform = "generic"
    if "leetcode" in normalized or "class solution" in normalized:
        platform = "leetcode"
    elif "hackerrank" in normalized:
        platform = "hackerrank"

    python_match = _PYTHON_DEF_RE.search(combined)
    python_function_name = python_match.group(1) if python_match else ""
    python_function_params = (
        [part.strip().split("=", 1)[0].strip() for part in python_match.group(2).split(",") if part.strip()]
        if python_match
        else []
    )
    class_solution_detected = bool(re.search(r"\bclass\s+solution\b", combined, re.IGNORECASE))
    public_static_detected = bool(re.search(r"\bpublic\s+static\b", combined, re.IGNORECASE))
    js_function_match = _JS_FUNCTION_RE.search(combined)
    generic_function_match = re.search(r"\bcomplete\s+the\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+function\b", normalized)
    named_completion_match = re.search(
        r"\bcomplete\s+the\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
        combined,
        re.IGNORECASE,
    )
    function_parameters_match = re.search(
        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+has\s+the\s+following\s+parameters\b",
        combined,
        re.IGNORECASE,
    )

    named_completion_name = named_completion_match.group(1) if named_completion_match else ""
    if named_completion_name.lower() in {"function", "code", "stub"}:
        named_completion_name = ""
    function_name = (
        python_function_name
        or (js_function_match.group(1) if js_function_match else "")
        or (generic_function_match.group(1) if generic_function_match else "")
        or named_completion_name
        or (function_parameters_match.group(1) if function_parameters_match else "")
    )

    stub_phrase_patterns = (
        r"complete the function",
        r"only necessary to complete the function",
        r"complete the [a-zA-Z_][a-zA-Z0-9_]* function",
        r"the code stub provided",
        r"function is expected to return",
        r"function accepts",
        r"function description",
        r"has the following parameters",
    )
    stub_phrase_detected = any(re.search(pattern, normalized) for pattern in stub_phrase_patterns)
    returns_phrase_detected = "returns" in normalized and ("function" in normalized or bool(function_name))
    function_stub_detected = bool(
        class_solution_detected
        or public_static_detected
        or python_match
        or js_function_match
        or stub_phrase_detected
        or returns_phrase_detected
    )

    stdin_markers = (
        "read input from stdin",
        "read from stdin",
        "input format",
        "output format",
    )
    stdin_full_solution_detected = any(marker in normalized for marker in stdin_markers)

    if class_solution_detected or "leetcode" in normalized:
        code_generation_mode = "leetcode_class"
    elif function_stub_detected:
        code_generation_mode = "function_stub"
    elif stdin_full_solution_detected:
        code_generation_mode = "stdin_full_solution"
    else:
        code_generation_mode = "unknown"

    return {
        "code_generation_mode": code_generation_mode,
        "function_stub_detected": function_stub_detected,
        "function_name": function_name or None,
        "function_params": python_function_params,
        "platform": platform,
        "language": language,
    }


def build_coding_input_contract(problem_text: str, editor_text: Optional[str] = None) -> dict:
    text = str(problem_text or "")
    normalized = text.lower()
    mode_detection = detect_code_generation_mode(problem_text, editor_text)
    language = mode_detection.get("language") or detect_programming_language(problem_text, editor_text)
    input_format_text = _section_between(
        text,
        "input format",
        ("output format", "constraints", "sample input", "sample output", "explanation"),
    )
    output_format_text = _section_between(
        text,
        "output format",
        ("constraints", "sample input", "sample output", "explanation"),
    )
    if "maximize it" in normalized:
        problem_family = "maximize_it"
    elif (
        "set .difference" in normalized
        or "difference() operation" in normalized
        or ("english newspaper" in normalized and "french newspaper" in normalized)
    ):
        problem_family = "set_difference"
    elif (
        "classes: dealing with complex numbers" in normalized
        or "class complex" in normalized
        or (
            "complex numbers" in normalized
            and (
                "__add__" in normalized
                or "__sub__" in normalized
                or "__mul__" in normalized
                or "__truediv__" in normalized
                or "operator" in normalized
                or "modulus" in normalized
            )
        )
        or "addition, subtraction, multiplication, division and modulus operations" in normalized
    ):
        problem_family = "complex_numbers_class"
    elif (
        "the minion game" in normalized
        or "minion_game" in normalized
        or ("kevin" in normalized and "stuart" in normalized and "vowels" in normalized)
        or "starting with vowels" in normalized
        or "starting with consonants" in normalized
    ):
        problem_family = "minion_game"
    elif "finding the percentage" in normalized:
        problem_family = "finding_the_percentage"
    elif "list comprehensions" in normalized:
        problem_family = "list_comprehensions"
    elif (
        "nested lists" in normalized
        or "second lowest grade" in normalized
        or "order their names alphabetically" in normalized
    ):
        problem_family = "nested_lists"
    else:
        problem_family = "generic"
    platform = mode_detection.get("platform") or (
        "hackerrank" if "hackerrank" in normalized else ("leetcode" if "leetcode" in normalized else "generic")
    )
    has_function_stub = bool(mode_detection.get("function_stub_detected"))
    code_generation_mode = str(mode_detection.get("code_generation_mode") or "unknown")
    if "standalone demonstration" in normalized and "no stdin input contract" in normalized:
        code_generation_mode = "standalone_demo"
    function_name = mode_detection.get("function_name")
    function_params = list(mode_detection.get("function_params") or [])
    if problem_family == "minion_game":
        has_function_stub = True
        code_generation_mode = "function_stub"
        function_name = "minion_game"
        function_params = function_params or ["string"]
    class_stub_detected = False
    class_name = None
    required_methods: list[str] = []
    output_format_requires_custom_complex = False
    output_decimal_places = None
    reject_builtin_complex_only_solution = False
    if problem_family == "complex_numbers_class":
        has_function_stub = False
        code_generation_mode = "class_stub"
        class_stub_detected = True
        class_name = "Complex"
        required_methods = list(_COMPLEX_REQUIRED_METHODS)
        output_format_requires_custom_complex = True
        output_decimal_places = 2
        reject_builtin_complex_only_solution = True

    first_line_vars: List[str] = []
    read_first_line_together = False
    separate_line_vars: List[str] = []
    read_each_var_separately = False
    first_line_match = re.search(
        r"first line contains(?: the integer)?\s+([A-Za-z0-9_,\s]+?)(?:\.|\n|$)",
        input_format_text,
        re.IGNORECASE,
    )
    if first_line_match:
        first_line_fragment = first_line_match.group(1)
        first_line_vars = extract_input_variables(first_line_fragment)
        if re.search(r"\bnumber\s+of\b", first_line_fragment, re.IGNORECASE) and not re.search(
            r"\binteger\s+[A-Za-z_][A-Za-z0-9_]*\b",
            first_line_fragment,
            re.IGNORECASE,
        ):
            first_line_vars = []
        read_first_line_together = len(first_line_vars) >= 2
    elif re.search(r"\bK\s+and\s+M\b", input_format_text, re.IGNORECASE):
        first_line_vars = ["K", "M"]
        read_first_line_together = True

    separate_line_match = re.search(
        r"((?:\b(?:two|three|four|five|six|seven|eight|nine|ten)\b|\b\d+\b)\s+integers?\s+[A-Za-z0-9_,\sand]+?,\s*each\s+on\s+a\s+separate\s+line)",
        input_format_text,
        re.IGNORECASE,
    )
    if separate_line_match:
        separate_line_vars = extract_input_variables(separate_line_match.group(1))
        read_each_var_separately = len(separate_line_vars) >= 2

    next_lines_have_count_prefix = bool(
        re.search(
            r"next\s+K\s+lines?.*integer\s+N[iI]\b.*followed\s+by\s+N[iI]\b.*space[- ]separated\s+integers",
            input_format_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if not next_lines_have_count_prefix:
        next_lines_have_count_prefix = bool(
            re.search(
                r"next\s+\w+\s+lines?.*count.*followed\s+by.*space[- ]separated\s+integers",
                input_format_text,
                re.IGNORECASE | re.DOTALL,
            )
        )

    count_prefix_name = "Ni" if re.search(r"\bN[iI]\b", input_format_text) else ("count_prefix" if next_lines_have_count_prefix else "")
    skip_count_prefix = next_lines_have_count_prefix
    count_value_pairs = bool(
        re.search(
            r"first\s+line\s+contains\s+(?:the\s+)?number.*?"
            r"second\s+line\s+contains\s+(?:the\s+)?space[- ]separated\s+list.*?"
            r"third\s+line\s+contains\s+(?:the\s+)?number.*?"
            r"fourth\s+line\s+contains\s+(?:the\s+)?space[- ]separated\s+list",
            input_format_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if problem_family == "set_difference":
        count_value_pairs = True
    records_count_prefix = bool(
        re.search(
            r"first\s+line\s+contains\s+(?:the\s+integer\s+)?n\b.*number\s+of\s+students|next\s+n\s+lines?.*names?.*marks?",
            input_format_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    final_line_vars: list[str] = []
    final_line_match = re.search(
        r"final\s+line\s+contains\s+(.+?)(?:\.|\n|$)",
        input_format_text,
        re.IGNORECASE,
    )
    if final_line_match:
        final_line_vars = extract_input_variables(final_line_match.group(1))

    output_kind = "unknown"
    if re.search(r"single integer|print a single integer", output_format_text, re.IGNORECASE):
        output_kind = "single_integer"
    elif re.search(r"2 decimal places|2 places after the decimal", output_format_text, re.IGNORECASE):
        output_kind = "two_decimal_places"
    elif re.search(r"print one line|single line", output_format_text, re.IGNORECASE):
        output_kind = "single_line"
    if problem_family == "minion_game":
        output_kind = "print_winner_score_or_draw"
    elif problem_family == "complex_numbers_class":
        output_kind = "custom_complex_two_decimal_i"

    output_context = "\n".join(part for part in (text, output_format_text) if part)
    output_context_normalized = output_context.lower()
    output_requires_sorting = bool(
        re.search(
            r"alphabetically|alphabetical order|lexicographic|lexicographically|sorted order|increasing order|decreasing order|order their names alphabetically",
            output_context_normalized,
        )
    )
    output_sort_order = None
    if re.search(r"alphabetically|alphabetical order|order their names alphabetically", output_context_normalized):
        output_sort_order = "alphabetical"
    elif re.search(r"lexicographic|lexicographically", output_context_normalized):
        output_sort_order = "lexicographic"
    elif "decreasing order" in output_context_normalized:
        output_sort_order = "descending"
    elif re.search(r"sorted order|increasing order", output_context_normalized):
        output_sort_order = "ascending"

    output_items_per_line = bool(
        re.search(r"print each .* on a new line|each .* on a new line|one per line|new line", output_context_normalized)
    )
    if problem_family == "nested_lists":
        output_requires_sorting = True
        output_sort_order = "alphabetical"
        output_items_per_line = True

    sample_tests = extract_sample_tests(text)
    input_steps: list[dict[str, Any]] = []
    if count_value_pairs:
        input_steps = [
            {
                "step": 1,
                "description": "read first count line",
                "variable_names": ["n"],
                "source": "stdin",
                "line_type": "single_integer",
                "ignore_or_skip": True,
            },
            {
                "step": 2,
                "description": "read first set values",
                "variable_names": ["english"],
                "source": "stdin",
                "line_type": "space_separated_values",
                "ignore_or_skip": False,
            },
            {
                "step": 3,
                "description": "read second count line",
                "variable_names": ["m"],
                "source": "stdin",
                "line_type": "single_integer",
                "ignore_or_skip": True,
            },
            {
                "step": 4,
                "description": "read second set values",
                "variable_names": ["french"],
                "source": "stdin",
                "line_type": "space_separated_values",
                "ignore_or_skip": False,
            },
        ]

    contract = {
        "platform": platform,
        "mode": code_generation_mode,
        "code_generation_mode": code_generation_mode,
        "problem_family": problem_family,
        "language": language,
        "input_steps": input_steps,
        "first_line": " ".join(first_line_vars),
        "read_first_line_together": read_first_line_together,
        "first_line_vars": first_line_vars,
        "read_each_var_separately": read_each_var_separately,
        "separate_line_vars": separate_line_vars,
        "list_lines_have_count_prefix": next_lines_have_count_prefix,
        "next_lines_have_count_prefix": next_lines_have_count_prefix,
        "count_prefix_name": count_prefix_name,
        "skip_count_prefix": skip_count_prefix,
        "records_count_prefix": records_count_prefix,
        "records_count_name": "n" if records_count_prefix else "",
        "count_value_pairs": count_value_pairs,
        "count_value_pair_count": 2 if count_value_pairs else 0,
        "count_lines_are_metadata": count_value_pairs,
        "final_line": " ".join(final_line_vars),
        "final_line_vars": final_line_vars,
        "output": output_kind,
        "output_kind": output_kind,
        "output_requires_sorting": output_requires_sorting,
        "output_sort_order": output_sort_order,
        "output_items_per_line": output_items_per_line,
        "input_format_excerpt": input_format_text[:700],
        "output_format_excerpt": output_format_text[:400],
        "has_function_stub": has_function_stub,
        "function_stub_detected": has_function_stub,
        "function_name": function_name,
        "function_params": function_params,
        "required_stub_preserved": has_function_stub,
        "class_stub_detected": class_stub_detected,
        "class_name": class_name,
        "required_methods": required_methods,
        "output_format_requires_custom_complex": output_format_requires_custom_complex,
        "output_decimal_places": output_decimal_places,
        "reject_builtin_complex_only_solution": reject_builtin_complex_only_solution,
        "sample_tests": sample_tests,
        "sample_tests_source": "regex" if sample_tests else "none",
    }
    return contract


def merge_coding_contracts(regex_contract: dict, llm_contract: dict) -> dict:
    merged = dict(regex_contract or {})
    conflicts: list[str] = []
    llm = _coerce_llm_contract(
        llm_contract,
        used=bool((llm_contract or {}).get("llm_contract_used") or llm_contract),
    )

    for key in ("platform", "language", "problem_family"):
        regex_value = merged.get(key)
        llm_value = llm.get(key)
        if llm_value and llm_value not in {"generic", "unknown", ""}:
            if regex_value and regex_value not in {"generic", "unknown", llm_value}:
                conflicts.append(f"{key}: regex={regex_value} llm={llm_value}")
            if regex_value in {None, "", "generic", "unknown"}:
                merged[key] = llm_value

    llm_mode = llm.get("mode")
    regex_mode = merged.get("code_generation_mode") or merged.get("mode")
    if llm_mode and llm_mode not in {"unknown", ""}:
        if regex_mode and regex_mode not in {"unknown", llm_mode}:
            conflicts.append(f"mode: regex={regex_mode} llm={llm_mode}")
        if regex_mode in {None, "", "unknown"}:
            merged["mode"] = llm_mode
            merged["code_generation_mode"] = llm_mode

    if merged.get("function_stub_detected") or merged.get("mode") == "function_stub":
        merged["mode"] = "function_stub"
        merged["code_generation_mode"] = "function_stub"
    else:
        stub_rules = llm.get("stub_rules") or {}
        if stub_rules.get("has_stub"):
            merged["mode"] = "function_stub"
            merged["code_generation_mode"] = "function_stub"
            merged["function_stub_detected"] = True
            merged["function_name"] = merged.get("function_name") or stub_rules.get("function_name")
            if stub_rules.get("function_params") and not merged.get("function_params"):
                merged["function_params"] = stub_rules.get("function_params")

    if merged.get("problem_family") == "minion_game":
        merged["mode"] = "function_stub"
        merged["code_generation_mode"] = "function_stub"
        merged["function_stub_detected"] = True
        merged["has_function_stub"] = True
        merged["function_name"] = merged.get("function_name") or "minion_game"
        merged["function_params"] = merged.get("function_params") or ["string"]
        merged["output_kind"] = merged.get("output_kind") or "print_winner_score_or_draw"
        merged["output"] = merged.get("output") or "print_winner_score_or_draw"

    if merged.get("problem_family") == "complex_numbers_class":
        merged["mode"] = "class_stub"
        merged["code_generation_mode"] = "class_stub"
        merged["class_stub_detected"] = True
        merged["class_name"] = merged.get("class_name") or "Complex"
        merged["required_methods"] = merged.get("required_methods") or list(_COMPLEX_REQUIRED_METHODS)
        merged["output_format_requires_custom_complex"] = True
        merged["output_decimal_places"] = merged.get("output_decimal_places") or 2
        merged["reject_builtin_complex_only_solution"] = True
        merged["output_kind"] = merged.get("output_kind") or "custom_complex_two_decimal_i"
        merged["output"] = merged.get("output") or "custom_complex_two_decimal_i"

    input_steps = list(merged.get("input_steps") or [])
    for step in llm.get("input_steps") or []:
        if isinstance(step, dict) and step not in input_steps:
            input_steps.append(step)
    merged["input_steps"] = input_steps

    count_step_count = sum(
        1 for step in input_steps
        if isinstance(step, dict) and bool(step.get("ignore_or_skip")) and step.get("line_type") == "single_integer"
    )
    value_step_count = sum(
        1 for step in input_steps
        if isinstance(step, dict) and step.get("line_type") in {"space_separated_values", "count_then_values"}
    )
    critical_constraints = [str(item) for item in llm.get("critical_constraints") or []]
    if (
        count_step_count >= 2
        and value_step_count >= 2
        or any("count line" in item.lower() for item in critical_constraints)
    ):
        merged["count_value_pairs"] = True
        merged["count_value_pair_count"] = max(merged.get("count_value_pair_count") or 0, count_step_count)
        merged["count_lines_are_metadata"] = True

    regex_samples = list((regex_contract or {}).get("sample_tests") or [])
    llm_samples = list(llm.get("sample_tests") or [])
    if regex_samples:
        merged["sample_tests"] = regex_samples
        merged["sample_tests_source"] = "regex"
    elif llm_samples:
        merged["sample_tests"] = llm_samples
        merged["sample_tests_source"] = "llm"
    else:
        merged["sample_tests"] = []
        merged["sample_tests_source"] = "none"

    for key in ("output_rules", "ordering_rules", "critical_constraints", "task_summary", "stub_rules"):
        if llm.get(key) and not merged.get(key):
            merged[key] = llm.get(key)

    merged["regex_contract"] = regex_contract or {}
    merged["llm_contract_used"] = bool(llm.get("llm_contract_used"))
    merged["llm_contract"] = llm
    merged["contract_conflicts"] = conflicts
    return merged


def validate_submission_code_against_contract(code: str, contract: dict) -> dict:
    code_text = str(code or "")
    normalized = code_text.lower()
    language = str(contract.get("language") or "python").strip().lower()
    if language not in {"", "python"}:
        return {
            "passed": True,
            "errors": [],
            "python_syntax_validation_used": False,
            "python_syntax_valid": None,
            "incomplete_code_detected": False,
            "incomplete_code_errors": [],
            "editor_stub_validation_used": False,
            "editor_stub_validation_passed": None,
            "editor_stub_validation_errors": [],
            "required_stub_preserved": None,
            "standalone_solution_rejected": False,
            "function_stub_completeness_validation_used": False,
            "function_stub_completeness_passed": None,
            "function_stub_completeness_errors": [],
            "duplicate_function_definition_detected": False,
            "partial_function_snippet_detected": False,
            "class_stub_detected": bool(contract.get("class_stub_detected")),
            "class_name": contract.get("class_name"),
            "required_methods": contract.get("required_methods") or [],
            "missing_required_methods": [],
            "custom_class_validation_used": False,
            "custom_class_validation_passed": None,
            "custom_class_validation_errors": [],
            "builtin_complex_only_rejected": False,
            "output_format_requires_custom_complex": bool(contract.get("output_format_requires_custom_complex")),
            "output_decimal_places": contract.get("output_decimal_places"),
            "output_order_validation_used": False,
            "output_order_validation_passed": None,
            "output_order_validation_errors": [],
        }
    python_validation = validate_python_code_completeness(code_text)
    python_syntax_validation_used = True
    errors: List[str] = []
    editor_stub_contract = contract.get("editor_stub_contract") or contract
    editor_validation = validate_editor_stub_completion(code_text, editor_stub_contract)
    editor_stub_validation_used = bool(editor_validation.get("editor_stub_validation_used"))
    editor_stub_validation_errors = list(editor_validation.get("editor_stub_validation_errors") or [])
    if editor_stub_validation_errors:
        errors.extend(editor_stub_validation_errors)
    standalone_solution_rejected = False
    required_stub_preserved = None
    function_stub_completeness_validation_used = bool(
        contract.get("mode") == "function_stub" or contract.get("code_generation_mode") == "function_stub"
    )
    function_stub_completeness_errors: list[str] = []
    duplicate_function_definition_detected = False
    partial_function_snippet_detected = False
    custom_class_validation_used = bool(contract.get("problem_family") == "complex_numbers_class")
    custom_class_validation_errors: list[str] = []
    missing_required_methods: list[str] = []
    builtin_complex_only_rejected = False
    output_order_validation_used = bool(contract.get("problem_family") == "nested_lists")
    output_order_validation_errors: list[str] = []
    output_order_validation_passed = True

    if not python_validation["passed"]:
        errors.extend(python_validation["errors"])
        return {
            "passed": False,
            "errors": errors,
            "python_syntax_validation_used": python_syntax_validation_used,
            "python_syntax_valid": python_validation["python_syntax_valid"],
            "incomplete_code_detected": python_validation["incomplete_code_detected"],
            "incomplete_code_errors": list(python_validation["errors"]),
            "editor_stub_validation_used": editor_stub_validation_used,
            "editor_stub_validation_passed": not editor_stub_validation_errors,
            "editor_stub_validation_errors": editor_stub_validation_errors,
            "required_stub_preserved": required_stub_preserved,
            "standalone_solution_rejected": standalone_solution_rejected,
            "function_stub_completeness_validation_used": function_stub_completeness_validation_used,
            "function_stub_completeness_passed": not function_stub_completeness_errors,
            "function_stub_completeness_errors": function_stub_completeness_errors,
            "duplicate_function_definition_detected": duplicate_function_definition_detected,
            "partial_function_snippet_detected": partial_function_snippet_detected,
            "class_stub_detected": bool(contract.get("class_stub_detected")),
            "class_name": contract.get("class_name"),
            "required_methods": contract.get("required_methods") or [],
            "missing_required_methods": missing_required_methods,
            "custom_class_validation_used": custom_class_validation_used,
            "custom_class_validation_passed": not custom_class_validation_errors,
            "custom_class_validation_errors": custom_class_validation_errors,
            "builtin_complex_only_rejected": builtin_complex_only_rejected,
            "output_format_requires_custom_complex": bool(contract.get("output_format_requires_custom_complex")),
            "output_decimal_places": contract.get("output_decimal_places"),
            "output_order_validation_used": output_order_validation_used,
            "output_order_validation_passed": output_order_validation_passed,
            "output_order_validation_errors": output_order_validation_errors,
        }

    if function_stub_completeness_validation_used:
        function_name = str(contract.get("function_name") or "").strip()
        function_params = [str(param).strip() for param in contract.get("function_params") or [] if str(param).strip()]
        required_def_pattern = (
            rf"(?m)^[ \t]*def\s+{re.escape(function_name)}\s*\(([^)]*)\)\s*:"
            if function_name
            else r"(?m)^[ \t]*def\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*:"
        )
        required_def_matches = list(re.finditer(required_def_pattern, code_text))
        required_stub_preserved = bool(
            required_def_matches
        )

        if len(required_def_matches) > 1:
            duplicate_function_definition_detected = True
            function_stub_completeness_errors.append("Duplicate or nested required function definition detected.")

        has_standalone_io = ("input()" in normalized or "sys.stdin" in normalized) and "print(" in normalized
        if function_name and not required_stub_preserved:
            partial_function_snippet_detected = bool(
                re.search(r"(?m)^\s*(if|elif|else|for|while|return|print)\b", code_text)
            )
            function_stub_completeness_errors.append(
                f"Function-stub problem requires full function definition: def {function_name}(...)."
            )
        elif not required_stub_preserved:
            partial_function_snippet_detected = True
            function_stub_completeness_errors.append("Function-stub problem requires full function definition.")
        if has_standalone_io and not required_stub_preserved:
            standalone_solution_rejected = True
            function_stub_completeness_errors.append("Standalone stdin/print solution rejected for function-stub problem.")

        if required_stub_preserved and function_params:
            signature_params = [
                part.strip().split("=", 1)[0].strip()
                for part in str(required_def_matches[0].group(1) or "").split(",")
                if part.strip()
            ]
            if signature_params[: len(function_params)] != function_params:
                function_stub_completeness_errors.append(
                    f"Required function signature should preserve parameters: def {function_name}({', '.join(function_params)})."
                )

        if required_stub_preserved:
            function_body_after_def = code_text[required_def_matches[0].end():].strip()
            body_without_comments = re.sub(r"(?m)^\s*#.*$", "", function_body_after_def).strip()
            if not body_without_comments or re.fullmatch(r"pass", body_without_comments, flags=re.IGNORECASE):
                partial_function_snippet_detected = True
                function_stub_completeness_errors.append("Function-stub body is incomplete.")

        if contract.get("problem_family") == "minion_game" and required_stub_preserved:
            has_loop = bool(re.search(r"\bfor\s+\w+\s+in\s+range\s*\(", normalized))
            has_len_score = bool(re.search(r"len\s*\(\s*string\s*\)|\bn\s*-\s*\w+\b", normalized))
            has_players = "kevin" in normalized and "stuart" in normalized
            has_print_result = "print(" in normalized and ("draw" in normalized or "kevin" in normalized or "stuart" in normalized)
            if not (has_loop and has_len_score and has_players and has_print_result):
                partial_function_snippet_detected = True
                function_stub_completeness_errors.append("Minion Game function must compute Kevin/Stuart scores and print the winner or Draw.")

        errors.extend(function_stub_completeness_errors)
    elif contract.get("mode") == "leetcode_class":
        required_stub_preserved = bool(re.search(r"\bclass\s+Solution\b", code_text, re.IGNORECASE))
        if not required_stub_preserved:
            errors.append("Required LeetCode class stub missing: class Solution.")
    elif contract.get("mode") == "class_stub" and not custom_class_validation_used:
        class_name = str(contract.get("class_name") or "").strip()
        if class_name and not re.search(rf"(?m)^[ \t]*class\s+{re.escape(class_name)}\b", code_text):
            errors.append(f"Required class stub missing: class {class_name}.")
    elif contract.get("mode") == "stdin_full_solution":
        if "input()" not in normalized and "sys.stdin" not in normalized:
            errors.append("stdin/stdout problems must parse input from stdin.")

    if custom_class_validation_used:
        class_name = str(contract.get("class_name") or "Complex").strip()
        required_methods = list(contract.get("required_methods") or _COMPLEX_REQUIRED_METHODS)
        has_class = bool(re.search(rf"(?m)^[ \t]*class\s+{re.escape(class_name)}\b", code_text))
        uses_builtin_complex = bool(re.search(r"\bcomplex\s*\(", normalized))
        if not has_class:
            custom_class_validation_errors.append(f"Required custom class missing: class {class_name}.")
        if uses_builtin_complex and not has_class:
            builtin_complex_only_rejected = True
            custom_class_validation_errors.append("Built-in complex() only solution rejected for custom Complex class problem.")

        for method in required_methods:
            method_pattern = rf"(?m)^[ \t]*def\s+{re.escape(method)}\s*\("
            if not re.search(method_pattern, code_text):
                missing_required_methods.append(method)

        if "__str__" in missing_required_methods:
            custom_class_validation_errors.append("Custom Complex output formatting requires __str__.")
        for method in missing_required_methods:
            if method == "__str__":
                continue
            custom_class_validation_errors.append(f"Custom Complex class missing required method: {method}.")

        if has_class and contract.get("output_format_requires_custom_complex"):
            has_i_format = bool(re.search(r"i[\"']|%\.2f|:\.2f|0\.00", code_text))
            if not has_i_format:
                custom_class_validation_errors.append("Custom Complex output must use i format with two decimal places.")
            if re.search(r"\bj\b|complex\s*\.__str__|str\s*\(\s*complex\s*\(", normalized):
                custom_class_validation_errors.append("Custom Complex output must use i format, not Python j format.")
            if re.search(r"[\"'][^\"']*\s[+\-]\s[^\"']*i[^\"']*[\"']", code_text):
                custom_class_validation_errors.append("Custom Complex output must not include spaces around the sign.")

        if has_class:
            mod_match = re.search(
                r"(?ms)^[ \t]*def\s+mod\s*\([^)]*\)\s*:(.*?)(?=^[ \t]*def\s+|\Z)",
                code_text,
            )
            mod_body = mod_match.group(1) if mod_match else ""
            if mod_body and not re.search(r"return\s+Complex\s*\(", mod_body):
                custom_class_validation_errors.append("Complex.mod() must return a Complex value, not a plain float.")
            if mod_body and not re.search(r"sqrt\s*\(|\*\*\s*0\.5", mod_body):
                custom_class_validation_errors.append("Complex.mod() must compute sqrt(real^2 + imaginary^2).")

        direct_builtin_prints = bool(
            re.search(r"print\s*\(\s*f?[\"']?\{?\s*\w+\s*[+\-*/]\s*\w+", normalized)
            or re.search(r"print\s*\(\s*abs\s*\(\s*\w+\s*\)", normalized)
        )
        if direct_builtin_prints and not has_class:
            custom_class_validation_errors.append("Custom Complex class problem requires class methods and formatted string output.")

        input_call_count = len(re.findall(r"\binput\s*\(", code_text))
        if input_call_count > 2:
            custom_class_validation_errors.append("Complex runner must read exactly two input lines; duplicate input-reading blocks are rejected.")
        if input_call_count == 2:
            required_runner_fragments = ("x+y", "x-y", "x*y", "x/y", "x.mod()", "y.mod()")
            compact_code = re.sub(r"\s+", "", code_text)
            missing_runner_fragments = [
                fragment
                for fragment in required_runner_fragments
                if fragment not in compact_code
            ]
            if missing_runner_fragments:
                custom_class_validation_errors.append(
                    "Complex runner must print x+y, x-y, x*y, x/y, x.mod(), and y.mod()."
                )

        errors.extend(custom_class_validation_errors)

    if contract.get("read_first_line_together"):
        vars_ = [str(value).lower() for value in contract.get("first_line_vars") or []]
        if len(vars_) >= 2:
            separate_reads = all(re.search(rf"\b{re.escape(name)}\s*=\s*int\(input\(\)\)", normalized) for name in vars_[:2])
            if separate_reads:
                errors.append(f"{' and '.join(contract.get('first_line_vars')[:2])} must be read from the same line.")
            same_line_pattern = rf"{re.escape(vars_[0])}\s*,\s*{re.escape(vars_[1])}\s*=\s*(?:map\(int,\s*input\(\)\.split\(\)\)|\[int\(x\)\s+for\s+x\s+in\s+input\(\)\.split\(\)\])"
            if not re.search(same_line_pattern, normalized):
                errors.append(f"{' and '.join(contract.get('first_line_vars')[:2])} should be parsed together from one input line.")

    if contract.get("read_each_var_separately"):
        vars_ = [str(value).lower() for value in contract.get("separate_line_vars") or []]
        if len(vars_) >= 2:
            joined_vars_pattern = r"\s*,\s*".join(re.escape(name) for name in vars_)
            combined_assignment = rf"{joined_vars_pattern}\s*=\s*(?:map\(int,\s*input\(\)\.split\(\)\)|\[int\(x\)\s+for\s+x\s+in\s+input\(\)\.split\(\)\])"
            if re.search(combined_assignment, normalized):
                errors.append(f"{', '.join(contract.get('separate_line_vars'))} must each be read from separate input() lines.")
            for name in vars_:
                if not re.search(rf"\b{re.escape(name)}\s*=\s*int\(input\(\)\)", normalized):
                    errors.append(f"{name} should be read with its own int(input()) call.")

    if contract.get("problem_family") == "maximize_it" or contract.get("skip_count_prefix"):
        if re.search(r"lists\s*=\s*\[\s*list\s*\(\s*map\s*\(\s*int\s*,\s*input\(\)\.split\(\)\s*\)\s*\)\s*for\s*_+\s*in\s*range\(\s*k\s*\)\s*\]", normalized):
            errors.append("Each list line starts with Ni, so the first value must be skipped.")
        if re.search(r"append\s*\(\s*list\s*\(\s*map\s*\(\s*int\s*,\s*input\(\)\.split\(\)\s*\)\s*\)\s*\)", normalized):
            errors.append("Each list line starts with Ni, so the first value must be skipped.")
        if not re.search(r"(data|arr|nums|line|values)\s*\[\s*1\s*:\s*\]", normalized):
            errors.append("Each list line should slice off the count prefix using [1:].")

    if contract.get("problem_family") == "set_difference" or contract.get("count_value_pairs"):
        count_reads = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*int\s*\(\s*input\(\)\s*\)", code_text)
        set_value_reads = re.findall(
            r"set\s*\(\s*map\s*\(\s*int\s*,\s*input\(\)\.split\(\)\s*\)\s*\)",
            normalized,
        )
        reads_sets_directly = len(re.findall(r"set\s*\(\s*input\(\)\.split\(\)\s*\)", normalized)) >= 2
        has_set_difference = bool(re.search(r"\b\w+\s*-\s*\w+\b|\.difference\s*\(", normalized))
        if len(count_reads) < 2:
            errors.append("Count lines must be read before set value lines.")
        if reads_sets_directly:
            errors.append("Set value lines should parse integers with set(map(int, input().split())).")
        if len(set_value_reads) < 2:
            errors.append("Both set value lines should be read after their count lines.")
        if not has_set_difference:
            errors.append("Set Difference must output the size of the first set minus the second set.")

    if contract.get("problem_family") == "finding_the_percentage":
        if not re.search(r"\bn\s*=\s*int\(input\(\)\)", normalized):
            errors.append("Finding the Percentage must read n with int(input()).")
        if not re.search(r"for\s+_?\w*\s+in\s+range\(\s*n\s*\)", normalized):
            errors.append("Finding the Percentage must read n student records in a loop.")
        if not re.search(r"\bquery_name\s*=\s*input\(\)", normalized):
            errors.append("Finding the Percentage must read query_name from the final input line.")
        prints_two_decimals = bool(
            re.search(r"print\s*\(\s*(?:f[\"'][^\"']*\{[^}]+:\.2f\}|[\"'][^\"']*\{:.2f\}[^\"']*[\"']\.format\()", normalized)
            or re.search(r"print\s*\(\s*format\([^)]*,\s*[\"']\.2f[\"']\s*\)", normalized)
            or re.search(r"print\s*\(\s*round\([^)]*,\s*2\s*\)", normalized)
        )
        if not prints_two_decimals:
            errors.append("Finding the Percentage must print the average formatted to 2 decimal places.")

    if output_order_validation_used:
        selected_names_sorted = bool(
            re.search(r"\b\w*names?\w*\s*=\s*sorted\s*\(", normalized)
            or re.search(r"\b\w*names?\w*\.sort\s*\(", normalized)
            or re.search(r"\bsorted_students\s*=\s*sorted\s*\(", normalized)
            or re.search(r"for\s+\w+(?:\s*,\s*\w+)?\s+in\s+sorted\s*\(", normalized)
        )
        if not selected_names_sorted:
            output_order_validation_errors.append("Output must be sorted alphabetically before printing.")

        if contract.get("output_items_per_line"):
            prints_items_per_line = bool(
                re.search(r"for\s+\w+\s+in\s+(?:\w+|sorted\s*\([^)]*\))\s*:\s*\n\s*print\s*\(\s*\w+\s*\)", code_text)
                or re.search(r"print\s*\(\s*['\"]\\n['\"]\.join\s*\(", normalized)
            )
            if not prints_items_per_line:
                output_order_validation_errors.append("Each matching name should be printed on a new line.")

        output_order_validation_passed = not output_order_validation_errors
        errors.extend(output_order_validation_errors)

    return {
        "passed": not errors,
        "errors": errors,
        "python_syntax_validation_used": python_syntax_validation_used,
        "python_syntax_valid": python_validation["python_syntax_valid"],
        "incomplete_code_detected": python_validation["incomplete_code_detected"],
        "incomplete_code_errors": list(python_validation["errors"]),
        "editor_stub_validation_used": editor_stub_validation_used,
        "editor_stub_validation_passed": not editor_stub_validation_errors,
        "editor_stub_validation_errors": editor_stub_validation_errors,
        "required_stub_preserved": required_stub_preserved,
        "standalone_solution_rejected": standalone_solution_rejected,
        "function_stub_completeness_validation_used": function_stub_completeness_validation_used,
        "function_stub_completeness_passed": not function_stub_completeness_errors,
        "function_stub_completeness_errors": function_stub_completeness_errors,
        "duplicate_function_definition_detected": duplicate_function_definition_detected,
        "partial_function_snippet_detected": partial_function_snippet_detected,
        "class_stub_detected": bool(contract.get("class_stub_detected")),
        "class_name": contract.get("class_name"),
        "required_methods": contract.get("required_methods") or [],
        "missing_required_methods": missing_required_methods,
        "custom_class_validation_used": custom_class_validation_used,
        "custom_class_validation_passed": not custom_class_validation_errors,
        "custom_class_validation_errors": custom_class_validation_errors,
        "builtin_complex_only_rejected": builtin_complex_only_rejected,
        "output_format_requires_custom_complex": bool(contract.get("output_format_requires_custom_complex")),
        "output_decimal_places": contract.get("output_decimal_places"),
        "output_order_validation_used": output_order_validation_used,
        "output_order_validation_passed": output_order_validation_passed,
        "output_order_validation_errors": output_order_validation_errors,
    }


def extract_sample_tests(problem_text: str) -> list[dict]:
    text = str(problem_text or "")
    matches = list(_SECTION_BREAK_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        label = match.group(1).strip().lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((label, body))

    sample_tests: list[dict] = []
    pending_input = None
    for label, body in sections:
        if label.startswith("sample input"):
            pending_input = body
        elif label.startswith("sample output") and pending_input is not None:
            sample_tests.append({
                "input": pending_input.strip(),
                "expected_output": body.strip(),
            })
            pending_input = None
    return sample_tests


def build_function_stub_test_harness(code: str, contract: Optional[dict] = None) -> dict:
    contract = contract or {}
    function_name = str(contract.get("function_name") or "").strip()
    class_name = str(contract.get("class_name") or "").strip()
    mode = str(contract.get("mode") or contract.get("code_generation_mode") or "")
    code_text = str(code or "")
    if contract.get("problem_family") == "complex_numbers_class" and class_name == "Complex":
        if "__main__" in code_text or re.search(r"\binput\s*\(\s*\)", code_text):
            return {"code": code_text, "used": False, "function_name": None, "class_name": None}
        if not re.search(r"(?m)^[ \t]*class\s+Complex\b", code_text):
            return {"code": code_text, "used": False, "function_name": None, "class_name": None}
        harness = (
            "\n\nif __name__ == \"__main__\":\n"
            "    c = map(float, input().split())\n"
            "    d = map(float, input().split())\n"
            "    x = Complex(*c)\n"
            "    y = Complex(*d)\n"
            "    print(*map(str, [x + y, x - y, x * y, x / y, x.mod(), y.mod()]), sep=\"\\n\")\n"
        )
        return {
            "code": f"{code_text.rstrip()}{harness}",
            "used": True,
            "function_name": None,
            "class_name": "Complex",
        }

    if mode != "function_stub" or not function_name:
        return {"code": code_text, "used": False, "function_name": None, "class_name": None}
    if "input()" in code_text.lower() or "__main__" in code_text:
        return {"code": code_text, "used": False, "function_name": None, "class_name": None}
    if not re.search(rf"(?m)^[ \t]*def\s+{re.escape(function_name)}\s*\(", code_text):
        return {"code": code_text, "used": False, "function_name": None, "class_name": None}

    if function_name == "minion_game":
        harness = (
            "\n\nif __name__ == \"__main__\":\n"
            "    s = input().strip()\n"
            "    minion_game(s)\n"
        )
    elif function_name == "is_leap":
        harness = (
            "\n\nif __name__ == \"__main__\":\n"
            "    year = int(input())\n"
            "    print(is_leap(year))\n"
        )
    else:
        return {"code": code_text, "used": False, "function_name": None, "class_name": None}

    return {
        "code": f"{code_text.rstrip()}{harness}",
        "used": True,
        "function_name": function_name,
        "class_name": None,
    }


def run_python_sample_tests(code: str, sample_tests: list[dict], contract: Optional[dict] = None) -> dict:
    code_text = str(code or "")
    if not sample_tests:
        return {
            "ran": False,
            "passed": False,
            "errors": ["no_sample_tests_found"],
            "skipped_reason": "no_sample_tests_found",
            "actual_output": None,
            "expected_output": None,
            "function_test_harness_used": False,
            "function_test_harness_name": None,
            "class_test_harness_used": False,
            "class_test_harness_name": None,
        }
    if _SUSPICIOUS_IMPORT_RE.search(code_text):
        return {
            "ran": False,
            "passed": False,
            "errors": ["unsafe_import_detected"],
            "skipped_reason": "unsafe_import_detected",
            "actual_output": None,
            "expected_output": None,
            "function_test_harness_used": False,
            "function_test_harness_name": None,
            "class_test_harness_used": False,
            "class_test_harness_name": None,
        }

    harness_result = build_function_stub_test_harness(code_text, contract)
    runnable_code = str(harness_result.get("code") or code_text)
    temp_path = None
    errors: list[str] = []
    first_actual = None
    first_expected = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
            handle.write(runnable_code)
            temp_path = handle.name

        for sample in sample_tests:
            completed = subprocess.run(
                [sys.executable, temp_path],
                input="\n".join(
                    line.strip()
                    for line in textwrap.dedent(str(sample.get("input", ""))).strip().splitlines()
                ),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=3,
                check=False,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            actual = str(completed.stdout or "").strip()
            expected = "\n".join(
                line.strip()
                for line in textwrap.dedent(str(sample.get("expected_output", ""))).strip().splitlines()
            )
            if first_actual is None:
                first_actual = actual
                first_expected = expected
            if completed.returncode != 0:
                errors.append(f"sample_runtime_error:{(completed.stderr or '').strip()[:240]}")
                if first_actual is None:
                    first_actual = actual
                    first_expected = expected
                continue
            if actual != expected:
                errors.append(f"sample_output_mismatch: expected={expected!r} actual={actual!r}")
                first_actual = actual
                first_expected = expected
        return {
            "ran": True,
            "passed": not errors,
            "errors": errors,
            "skipped_reason": "",
            "actual_output": first_actual,
            "expected_output": first_expected,
            "function_test_harness_used": bool(harness_result.get("used") and harness_result.get("function_name")),
            "function_test_harness_name": harness_result.get("function_name"),
            "class_test_harness_used": bool(harness_result.get("used") and harness_result.get("class_name")),
            "class_test_harness_name": harness_result.get("class_name"),
        }
    except subprocess.TimeoutExpired:
        return {
            "ran": True,
            "passed": False,
            "errors": ["sample_timeout"],
            "skipped_reason": "",
            "actual_output": first_actual,
            "expected_output": first_expected,
            "function_test_harness_used": bool(harness_result.get("used") and harness_result.get("function_name")),
            "function_test_harness_name": harness_result.get("function_name"),
            "class_test_harness_used": bool(harness_result.get("used") and harness_result.get("class_name")),
            "class_test_harness_name": harness_result.get("class_name"),
        }
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
