from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp.coding_quality_gate import (
    apply_hackerrank_context_gate,
    build_coding_input_contract,
    build_editor_stub_contract,
    build_hackerrank_problem_contract,
    clean_extracted_problem_text,
    detect_code_generation_mode,
    evaluate_hackerrank_context_readiness,
    extract_input_variables,
    extract_sample_tests,
    force_context_not_ready_for_json_noise,
    merge_coding_contracts,
    run_python_sample_tests,
    validate_editor_stub_completion,
    validate_python_code_completeness,
    validate_submission_code_against_contract,
)


def test_extract_input_variables_filters_input_format_words() -> None:
    assert extract_input_variables("The first line contains 2 space separated integers K and M.") == ["K", "M"]
    assert extract_input_variables("Four integers x, y, z and n, each on a separate line.") == ["x", "y", "z", "n"]
    assert extract_input_variables("The final line contains query_name, the name of a student to query.") == ["query_name"]
    assert extract_input_variables("The first line contains the integer n, the number of students.") == ["n"]


def test_detects_hackerrank_function_stub_mode_for_leap_year() -> None:
    problem_text = """
    HackerRank
    Write a function
    It is only necessary to complete the is_leap function.
    The function is expected to return a BOOLEAN.
    The function accepts INTEGER year as parameter.
    """
    editor_text = """
    def is_leap(year):
        leap = False

        # Write your logic here

        return leap

    year = int(input())
    print(is_leap(year))
    """

    detection = detect_code_generation_mode(problem_text, editor_text)
    contract = build_coding_input_contract(problem_text, editor_text)
    bad_code = "year = int(input())\nprint(year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))"
    good_code = "def is_leap(year):\n    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)"

    assert detection["code_generation_mode"] == "function_stub"
    assert detection["function_stub_detected"] is True
    assert detection["function_name"] == "is_leap"
    assert contract["code_generation_mode"] == "function_stub"

    bad_validation = validate_submission_code_against_contract(bad_code, contract)
    assert bad_validation["passed"] is False
    assert bad_validation["standalone_solution_rejected"] is True

    good_validation = validate_submission_code_against_contract(good_code, contract)
    assert good_validation["passed"] is True
    assert good_validation["required_stub_preserved"] is True


def test_builds_full_hackerrank_problem_contract_from_sections() -> None:
    problem_text = """
    HackerRank
    Maximize It!
    Run Code
    Task
    You are given K lists. Pick one element from each list and maximize the value modulo M.
    Concept
    Use product from itertools to enumerate combinations.
    Input Format
    The first line contains 2 space separated integers K and M.
    The next K lines each contains an integer Ni, followed by Ni space separated integers denoting the elements in the list.
    Constraints
    1 <= K <= 7
    Output Format
    Print the maximum value.
    Sample Input 0
    3 1000
    2 5 4
    3 7 8 9
    5 5 7 8 9 10
    Sample Output 0
    206
    Explanation
    Choosing 5, 9, and 10 gives 206.
    Submit Code
    """

    contract = build_hackerrank_problem_contract(problem_text, None, "Maximize It!", "python")

    assert contract["platform"] == "hackerrank"
    assert contract["hackerrank_contract_used"] is True
    assert contract["hackerrank_full_problem_used"] is True
    assert contract["problem_title"] == "Maximize It!"
    assert contract["concept_text"] == "Use product from itertools to enumerate combinations."
    assert contract["input_format"].startswith("The first line contains 2 space separated integers K and M.")
    assert contract["output_format"] == "Print the maximum value."
    assert contract["sample_tests"] == [
        {
            "input": "3 1000\n    2 5 4\n    3 7 8 9\n    5 5 7 8 9 10",
            "expected_output": "206",
        }
    ]
    assert contract["contract_sections_found"]["sample_input"] is True
    assert contract["contract_sections_found"]["sample_output"] is True
    assert contract["read_first_line_together"] is True
    assert contract["skip_count_prefix"] is True


def _map_and_lambda_editor_text() -> str:
    return """
cube = lambda x: # complete the lambda function

def fibonacci(n):
    # return a list of fibonacci numbers

if __name__ == '__main__':
    n = int(input())
    print(list(map(cube, fibonacci(n))))
"""


def _map_and_lambda_problem_text() -> str:
    return """
    HackerRank
    Map and Lambda Function
    Task
    Generate the first N fibonacci numbers, cube each using map and lambda, and print the list.
    Input Format
    One line of input: an integer N.
    Output Format
    Print a list on a single line.
    Sample Input 0
    5
    Sample Output 0
    [0, 1, 1, 8, 27]
    """


def _correct_map_and_lambda_code() -> str:
    return """
cube = lambda x: x ** 3

def fibonacci(n):
    result = []
    a = 0
    b = 1

    for _ in range(n):
        result.append(a)
        a, b = b, a + b

    return result

if __name__ == '__main__':
    n = int(input())
    print(list(map(cube, fibonacci(n))))
"""


def test_map_and_lambda_editor_stub_contract_detects_required_symbols() -> None:
    contract = build_editor_stub_contract(_map_and_lambda_editor_text())

    assert contract["editor_stub_used"] is True
    assert contract["code_generation_mode"] == "editor_stub_completion"
    assert contract["required_lambdas"] == ["cube"]
    assert contract["required_functions"] == ["fibonacci"]
    assert contract["editor_runner_detected"] is True
    assert "# complete the lambda function" in contract["placeholder_lines"]


def test_map_and_lambda_rejects_standalone_solution_that_ignores_stub() -> None:
    contract = build_hackerrank_problem_contract(
        _map_and_lambda_problem_text(),
        _map_and_lambda_editor_text(),
        "Map and Lambda Function",
        "python",
    )
    bad_code = """
n = int(input())
fib_sequence = [0, 1]
while len(fib_sequence) < n:
    fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])
print(list(map(lambda x: x**3, fib_sequence[:n])))
"""
    validation = validate_editor_stub_completion(bad_code, contract["editor_stub_contract"])

    assert contract["editor_stub_used"] is True
    assert contract["code_generation_mode"] == "editor_stub_completion"
    assert validation["passed"] is False
    assert "Editor starter code requires completing required symbol(s): cube, fibonacci." in validation["errors"]
    assert "Generated code ignored the HackerRank editor starter code; standalone solution rejected." in validation["errors"]


def test_generic_editor_stub_rejects_standalone_solution_that_ignores_required_function() -> None:
    editor_text = """
def solve(values):
    # write your code here

if __name__ == '__main__':
    values = list(map(int, input().split()))
    print(solve(values))
"""
    bad_code = """
values = list(map(int, input().split()))
print(max(values))
"""
    stub_contract = build_editor_stub_contract(editor_text)
    validation = validate_editor_stub_completion(bad_code, stub_contract)

    assert stub_contract["editor_stub_used"] is True
    assert stub_contract["required_functions"] == ["solve"]
    assert validation["passed"] is False
    assert "Editor starter code requires completing required symbol(s): solve." in validation["errors"]
    assert "Generated code ignored the HackerRank editor starter code; standalone solution rejected." in validation["errors"]


def test_map_and_lambda_accepts_stub_compatible_code_and_sample() -> None:
    contract = build_hackerrank_problem_contract(
        _map_and_lambda_problem_text(),
        _map_and_lambda_editor_text(),
        "Map and Lambda Function",
        "python",
    )
    code = _correct_map_and_lambda_code()
    validation = validate_submission_code_against_contract(code, contract)
    sample_result = run_python_sample_tests(code, contract["sample_tests"], contract)

    assert validation["passed"] is True
    assert validation["editor_stub_validation_used"] is True
    assert validation["editor_stub_validation_passed"] is True
    assert sample_result["ran"] is True
    assert sample_result["passed"] is True
    assert sample_result["actual_output"] == "[0, 1, 1, 8, 27]"


def test_generic_hackerrank_editor_comment_does_not_force_stub_mode() -> None:
    contract = build_hackerrank_problem_contract(
        """
        HackerRank
        Simple Input
        Input Format
        One integer x.
        Output Format
        Print x.
        """,
        "# Enter your code here. Read input from STDIN. Print output to STDOUT",
        "Simple Input",
        "python",
    )

    assert contract["editor_stub_used"] is False
    assert contract["editor_stub_mode"] == "generic_stdin"
    assert contract["code_generation_mode"] == "stdin_full_solution"


def test_runner_and_import_only_editor_does_not_force_stub_mode() -> None:
    contract = build_hackerrank_problem_contract(
        """
        HackerRank
        Class 2 - Find the Torsional Angle
        Input Format
        Four lines of three floats.
        Output Format
        Print the angle.
        """,
        """
        import math

        if __name__ == '__main__':
            pass
        """,
        "Class 2 - Find the Torsional Angle",
        "python",
    )

    assert contract["editor_stub_used"] is False
    assert contract["editor_stub_mode"] == "generic_stdin"
    assert contract["code_generation_mode"] == "stdin_full_solution"


def test_noisy_hackerrank_editor_ocr_is_ignored_as_generic_stdin() -> None:
    contract = build_hackerrank_problem_contract(
        """
        HackerRank
        Class 2 - Find the Torsional Angle
        Input Format
        Four lines of three floats.
        Output Format
        Print the angle.
        """,
        """
        Exit Full Screen View
        Language Python 3
        import math
        >if -_name mai
        Line:1 Col:1
        Upload CodeasFile
        RunCode
        SubmitCode
        """,
        "Class 2 - Find the Torsional Angle",
        "python",
    )

    assert contract["editor_stub_used"] is False
    assert contract["editor_stub_mode"] == "generic_stdin"
    assert contract["code_generation_mode"] == "stdin_full_solution"


def test_meaningful_editor_setup_lines_are_treated_as_stub_structure() -> None:
    editor_text = """
import re

TOKEN_RE = re.compile(r"\\w+")

@staticmethod
def solve(text):
    # write your code here
    pass
"""
    contract = build_editor_stub_contract(editor_text)

    assert contract["editor_stub_used"] is True
    assert contract["required_import_lines"] == ["import re"]
    assert contract["required_assignment_targets"] == ["TOKEN_RE"]
    assert contract["required_decorator_lines"] == ["@staticmethod"]


def test_meaningful_editor_setup_lines_must_be_preserved() -> None:
    editor_text = """
import re

TOKEN_RE = re.compile(r"\\w+")

def solve(text):
    # write your code here
    pass
"""
    bad_code = """
def solve(text):
    return text
"""
    validation = validate_editor_stub_completion(bad_code, build_editor_stub_contract(editor_text))

    assert validation["passed"] is False
    assert "Editor starter code requires preserving import/setup line(s): import re." in validation["errors"]
    assert "Editor starter code requires preserving assignment/setup symbol(s): TOKEN_RE." in validation["errors"]


def test_detects_stdin_full_solution_mode_for_maximize_it() -> None:
    problem_text = """
    HackerRank
    Maximize It!
    Input Format
    The first line contains 2 space separated integers K and M.
    The next K lines each contains an integer Ni, followed by Ni space separated integers denoting the elements in the list.
    Output Format
    Print the maximum value.
    Read input from STDIN.
    Sample Input 0
    3 1000
    2 5 4
    3 7 8 9
    5 5 7 8 9 10
    Sample Output 0
    206
    """

    detection = detect_code_generation_mode(problem_text)
    contract = build_coding_input_contract(problem_text)
    bad_code = "K = int(input())\nM = int(input())\nlists = [list(map(int, input().split())) for _ in range(K)]"
    code = """
from itertools import product

K, M = map(int, input().split())
lists = []
for _ in range(K):
    data = list(map(int, input().split()))
    nums = data[1:]
    lists.append(nums)

max_S = 0
for combination in product(*lists):
    value = sum(x ** 2 for x in combination) % M
    max_S = max(max_S, value)

print(max_S)
"""

    assert detection["code_generation_mode"] == "stdin_full_solution"
    assert detection["function_stub_detected"] is False
    assert contract["read_first_line_together"] is True
    assert contract["first_line_vars"] == ["K", "M"]
    assert contract["next_lines_have_count_prefix"] is True
    assert contract["skip_count_prefix"] is True
    bad_validation = validate_submission_code_against_contract(bad_code, contract)
    assert bad_validation["passed"] is False
    assert "K and M must be read from the same line." in bad_validation["errors"]
    assert "Each list line starts with Ni, so the first value must be skipped." in bad_validation["errors"]
    assert validate_submission_code_against_contract(code, contract)["passed"] is True
    sample_result = run_python_sample_tests(code, extract_sample_tests(problem_text))
    assert sample_result["ran"] is True
    assert sample_result["passed"] is True


def test_detects_separate_line_inputs_for_hackerrank_list_comprehensions() -> None:
    problem_text = """
    HackerRank
    List Comprehensions
    Input Format
    Four integers x, y, z and n, each on a separate line.
    Constraints
    Print the list in lexicographic increasing order.
    Sample Input 0
    1
    1
    1
    2
    Sample Output 0
    [[0, 0, 0], [0, 0, 1], [0, 1, 0], [1, 0, 0], [1, 1, 1]]
    """
    contract = build_coding_input_contract(problem_text)
    bad_code = "x, y, z, n = map(int, input().split())\nprint([[i, j, k] for i in range(x + 1) for j in range(y + 1) for k in range(z + 1) if i + j + k != n])"
    good_code = "x = int(input())\ny = int(input())\nz = int(input())\nn = int(input())\nprint([[i, j, k] for i in range(x + 1) for j in range(y + 1) for k in range(z + 1) if i + j + k != n])"

    assert contract["code_generation_mode"] == "stdin_full_solution"
    assert contract["read_each_var_separately"] is True
    assert contract["separate_line_vars"] == ["x", "y", "z", "n"]
    assert validate_submission_code_against_contract(bad_code, contract)["passed"] is False
    assert validate_submission_code_against_contract(good_code, contract)["passed"] is True
    sample_result = run_python_sample_tests(good_code, extract_sample_tests(problem_text))
    assert sample_result["ran"] is True
    assert sample_result["passed"] is True


def test_detects_finding_the_percentage_contract() -> None:
    problem_text = """
    HackerRank
    Finding the percentage
    Input Format
    The first line contains the integer n, the number of students.
    The next n lines contains the name and marks obtained by a student, each value separated by a space.
    The final line contains query_name, the name of a student to query.
    Output Format
    Print one line: The average of the marks obtained by the particular student correct to 2 decimal places.
    """
    contract = build_coding_input_contract(problem_text)
    bad_code = "n = int(input())\nstudent_marks = {}\nquery_name = input()\nprint(sum(student_marks[query_name]) / 3)"
    good_code = """
n = int(input())
student_marks = {}
for _ in range(n):
    name, *line = input().split()
    scores = list(map(float, line))
    student_marks[name] = scores
query_name = input()
average = sum(student_marks[query_name]) / len(student_marks[query_name])
print(f"{average:.2f}")
"""

    assert contract["problem_family"] == "finding_the_percentage"
    assert contract["records_count_prefix"] is True
    assert contract["records_count_name"] == "n"
    assert contract["final_line_vars"] == ["query_name"]
    assert contract["output_kind"] == "two_decimal_places"
    bad_validation = validate_submission_code_against_contract(bad_code, contract)
    assert bad_validation["passed"] is False
    assert "Finding the Percentage must read n student records in a loop." in bad_validation["errors"]
    assert "Finding the Percentage must print the average formatted to 2 decimal places." in bad_validation["errors"]
    assert validate_submission_code_against_contract(good_code, contract)["passed"] is True


def test_detects_nested_lists_output_order_contract() -> None:
    problem_text = """
    HackerRank
    Nested Lists
    Given the names and grades for each student in a class of N students, store them in a nested list and print the name(s) of any student(s) having the second lowest grade.
    If there are multiple students with the second lowest grade, order their names alphabetically and print each name on a new line.
    """

    contract = build_coding_input_contract(problem_text)

    assert contract["problem_family"] == "nested_lists"
    assert contract["output_requires_sorting"] is True
    assert contract["output_sort_order"] == "alphabetical"
    assert contract["output_items_per_line"] is True


def test_rejects_nested_lists_without_alphabetical_name_sorting() -> None:
    problem_text = """
    HackerRank
    Nested Lists
    If there are multiple students with the second lowest grade, order their names alphabetically and print each name on a new line.
    """
    contract = build_coding_input_contract(problem_text)
    bad_code = """
students = []
for _ in range(int(input())):
    name = input()
    score = float(input())
    students.append([name, score])

second_lowest = sorted(set([x[1] for x in students]))[1]
print('\\n'.join([x[0] for x in students if x[1] == second_lowest]))
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert validation["output_order_validation_used"] is True
    assert validation["output_order_validation_passed"] is False
    assert "Output must be sorted alphabetically before printing." in validation["errors"]


def test_accepts_nested_lists_with_alphabetical_name_sorting() -> None:
    problem_text = """
    HackerRank
    Nested Lists
    If there are multiple students with the second lowest grade, order their names alphabetically and print each name on a new line.
    """
    contract = build_coding_input_contract(problem_text)
    good_code = """
students = []
for _ in range(int(input())):
    name = input()
    score = float(input())
    students.append([name, score])

second_lowest = sorted(set(score for name, score in students))[1]
names = sorted(name for name, score in students if score == second_lowest)

for name in names:
    print(name)
"""
    validation = validate_submission_code_against_contract(good_code, contract)

    assert validation["passed"] is True
    assert validation["output_order_validation_used"] is True
    assert validation["output_order_validation_passed"] is True


def test_nested_lists_sample_order_runner() -> None:
    problem_text = """
    HackerRank
    Nested Lists
    If there are multiple students with the second lowest grade, order their names alphabetically and print each name on a new line.
    Sample Input 0
    5
    Harry
    37.21
    Berry
    37.21
    Tina
    37.2
    Akriti
    41
    Harsh
    39
    Sample Output 0
    Berry
    Harry
    """
    bad_code = """
students = []
for _ in range(int(input())):
    name = input()
    score = float(input())
    students.append([name, score])

second_lowest = sorted(set([x[1] for x in students]))[1]
print('\\n'.join([x[0] for x in students if x[1] == second_lowest]))
"""
    good_code = """
students = []
for _ in range(int(input())):
    name = input()
    score = float(input())
    students.append([name, score])

second_lowest = sorted(set(score for name, score in students))[1]
names = sorted(name for name, score in students if score == second_lowest)
for name in names:
    print(name)
"""

    assert run_python_sample_tests(bad_code, extract_sample_tests(problem_text))["passed"] is False
    assert run_python_sample_tests(good_code, extract_sample_tests(problem_text))["passed"] is True


def test_detects_leetcode_class_mode() -> None:
    problem_text = """
    LeetCode
    Given an array of integers nums and an integer target, return indices of the two numbers.
    class Solution:
        def twoSum(self, nums, target):
            pass
    """

    detection = detect_code_generation_mode(problem_text)

    assert detection["code_generation_mode"] == "leetcode_class"
    assert detection["function_stub_detected"] is True
    assert detection["platform"] == "leetcode"


def _set_difference_problem_text(include_sample: bool = True) -> str:
    sample = """
    Sample Input 0
    9
    1 2 3 4 5 6 7 8 9
    9
    10 1 2 3 11 21 55 6 8
    Sample Output 0
    4
    """ if include_sample else ""
    return f"""
    HackerRank
    Set .difference() Operation
    Input Format
    The first line contains the number of students who have subscribed to the English newspaper.
    The second line contains the space separated list of student roll numbers who have subscribed to the English newspaper.
    The third line contains the number of students who have subscribed to the French newspaper.
    The fourth line contains the space separated list of student roll numbers who have subscribed to the French newspaper.
    Output Format
    Output total number of students who have subscriptions to the English newspaper only.
    {sample}
    """


def test_detects_set_difference_count_value_contract_and_samples() -> None:
    regex_contract = build_coding_input_contract(_set_difference_problem_text())
    llm_contract = {
        "llm_contract_used": True,
        "platform": "hackerrank",
        "language": "python",
        "mode": "stdin_full_solution",
        "problem_family": "set_difference",
        "input_steps": [
            {"step": 1, "line_type": "single_integer", "variable_names": ["n"], "ignore_or_skip": True},
            {"step": 2, "line_type": "space_separated_values", "variable_names": ["english"], "ignore_or_skip": False},
            {"step": 3, "line_type": "single_integer", "variable_names": ["m"], "ignore_or_skip": True},
            {"step": 4, "line_type": "space_separated_values", "variable_names": ["french"], "ignore_or_skip": False},
        ],
        "sample_tests": [],
        "critical_constraints": ["do not ignore count lines"],
    }
    merged = merge_coding_contracts(regex_contract, llm_contract)

    assert merged["problem_family"] == "set_difference"
    assert merged["count_value_pairs"] is True
    assert merged["count_lines_are_metadata"] is True
    assert merged["sample_tests_source"] == "regex"
    assert len(merged["sample_tests"]) == 1


def test_rejects_set_difference_bad_code_and_passes_correct_code_sample() -> None:
    problem_text = _set_difference_problem_text()
    contract = build_coding_input_contract(problem_text)
    bad_code = """
set1 = set(input().split())
set2 = set(input().split())
print(len(set1 - set2))
"""
    good_code = """
n = int(input())
english = set(map(int, input().split()))

m = int(input())
french = set(map(int, input().split()))

print(len(english - french))
"""

    bad_validation = validate_submission_code_against_contract(bad_code, contract)
    assert bad_validation["passed"] is False
    assert "Count lines must be read before set value lines." in bad_validation["errors"]

    bad_sample_result = run_python_sample_tests(bad_code, extract_sample_tests(problem_text))
    assert bad_sample_result["ran"] is True
    assert bad_sample_result["passed"] is False
    assert bad_sample_result["expected_output"] == "4"

    assert validate_submission_code_against_contract(good_code, contract)["passed"] is True
    good_sample_result = run_python_sample_tests(good_code, extract_sample_tests(problem_text))
    assert good_sample_result["ran"] is True
    assert good_sample_result["passed"] is True


def test_no_sample_case_keeps_static_validation() -> None:
    contract = build_coding_input_contract(_set_difference_problem_text(include_sample=False))
    good_code = """
n = int(input())
english = set(map(int, input().split()))
m = int(input())
french = set(map(int, input().split()))
print(len(english - french))
"""

    assert contract["sample_tests"] == []
    assert contract["sample_tests_source"] == "none"
    assert validate_submission_code_against_contract(good_code, contract)["passed"] is True


def _minion_game_problem_text() -> str:
    return """
    HackerRank
    The Minion Game
    Kevin and Stuart want to play the minion game.
    Kevin has to make words starting with vowels.
    Stuart has to make words starting with consonants.
    Complete the minion_game in the editor below.
    Function Description
    minion_game has the following parameters:
    string string: the string to analyze
    Sample Input 0
    BANANA
    Sample Output 0
    Stuart 12
    """


def _minion_game_editor_text() -> str:
    return """
def minion_game(string):
    # your code goes here

if __name__ == '__main__':
    s = input()
    minion_game(s)
"""


def test_rejects_minion_game_partial_function_snippet() -> None:
    contract = build_coding_input_contract(_minion_game_problem_text(), _minion_game_editor_text())
    bad_code = """
if kevin_score > stuart_score:
    print(f"Kevin {kevin_score}")
elif stuart_score > kevin_score:
    print(f"Stuart {stuart_score}")
else:
    print("Draw")
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert contract["code_generation_mode"] == "function_stub"
    assert contract["function_name"] == "minion_game"
    assert contract["function_params"] == ["string"]
    assert validation["passed"] is False
    assert "Function-stub problem requires full function definition: def minion_game(...)." in validation["errors"]
    assert validation["partial_function_snippet_detected"] is True


def test_rejects_minion_game_duplicate_nested_function_def() -> None:
    contract = build_coding_input_contract(_minion_game_problem_text(), _minion_game_editor_text())
    bad_code = """
def minion_game(string):
    def minion_game(string):
        pass
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert "Duplicate or nested required function definition detected." in validation["errors"]
    assert validation["duplicate_function_definition_detected"] is True


def test_accepts_complete_minion_game_function() -> None:
    contract = build_coding_input_contract(_minion_game_problem_text(), _minion_game_editor_text())
    good_code = """
def minion_game(string):
    kevin_score = 0
    stuart_score = 0
    vowels = "AEIOU"
    n = len(string)

    for i in range(n):
        if string[i] in vowels:
            kevin_score += n - i
        else:
            stuart_score += n - i

    if kevin_score > stuart_score:
        print(f"Kevin {kevin_score}")
    elif stuart_score > kevin_score:
        print(f"Stuart {stuart_score}")
    else:
        print("Draw")
"""
    validation = validate_submission_code_against_contract(good_code, contract)

    assert validation["passed"] is True
    assert validation["function_stub_completeness_validation_used"] is True
    assert validation["function_stub_completeness_passed"] is True


def test_minion_game_sample_passes_with_function_stub_harness() -> None:
    problem_text = _minion_game_problem_text()
    contract = build_coding_input_contract(problem_text, _minion_game_editor_text())
    code = """
def minion_game(string):
    kevin_score = 0
    stuart_score = 0
    vowels = "AEIOU"
    n = len(string)
    for i in range(n):
        if string[i] in vowels:
            kevin_score += n - i
        else:
            stuart_score += n - i
    if kevin_score > stuart_score:
        print(f"Kevin {kevin_score}")
    elif stuart_score > kevin_score:
        print(f"Stuart {stuart_score}")
    else:
        print("Draw")
"""
    sample_result = run_python_sample_tests(code, extract_sample_tests(problem_text), contract)

    assert sample_result["ran"] is True
    assert sample_result["passed"] is True
    assert sample_result["function_test_harness_used"] is True
    assert sample_result["function_test_harness_name"] == "minion_game"


def test_leap_year_function_stub_sample_still_passes_with_harness() -> None:
    problem_text = """
    HackerRank
    Write a function
    It is only necessary to complete the is_leap function.
    Sample Input 0
    1990
    Sample Output 0
    False
    """
    editor_text = """
def is_leap(year):
    leap = False
    return leap
"""
    contract = build_coding_input_contract(problem_text, editor_text)
    code = """
def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
"""
    validation = validate_submission_code_against_contract(code, contract)
    sample_result = run_python_sample_tests(code, extract_sample_tests(problem_text), contract)

    assert validation["passed"] is True
    assert sample_result["ran"] is True
    assert sample_result["passed"] is True
    assert sample_result["function_test_harness_used"] is True
    assert sample_result["function_test_harness_name"] == "is_leap"


def _complex_numbers_problem_text() -> str:
    return """
    HackerRank
    Classes: Dealing with Complex Numbers
    You are given two complex numbers, and you have to print the result of their addition, subtraction, multiplication, division and modulus operations.
    The real and imaginary precision part should be correct up to two decimal places.
    You must overload the operators +, -, *, / and implement mod.
    Sample Input 0
    2 1
    5 6
    Sample Output 0
    7.00+7.00i
    -3.00-5.00i
    4.00+17.00i
    0.26-0.11i
    2.24+0.00i
    7.81+0.00i
    """


def _complex_numbers_editor_text() -> str:
    return """
class Complex(object):
    def __init__(self, real, imaginary):
        self.real = real
        self.imaginary = imaginary

    def __add__(self, no):
        pass

    def __sub__(self, no):
        pass

    def __mul__(self, no):
        pass

    def __truediv__(self, no):
        pass

    def mod(self):
        pass

    def __str__(self):
        pass
"""


def _correct_complex_class_code() -> str:
    return """
import math

class Complex:
    def __init__(self, real, imaginary):
        self.real = real
        self.imaginary = imaginary

    def __add__(self, other):
        return Complex(self.real + other.real, self.imaginary + other.imaginary)

    def __sub__(self, other):
        return Complex(self.real - other.real, self.imaginary - other.imaginary)

    def __mul__(self, other):
        real_part = self.real * other.real - self.imaginary * other.imaginary
        imaginary_part = self.real * other.imaginary + self.imaginary * other.real
        return Complex(real_part, imaginary_part)

    def __truediv__(self, other):
        denominator = other.real ** 2 + other.imaginary ** 2
        real_part = (self.real * other.real + self.imaginary * other.imaginary) / denominator
        imaginary_part = (self.imaginary * other.real - self.real * other.imaginary) / denominator
        return Complex(real_part, imaginary_part)

    def mod(self):
        return Complex(math.sqrt(self.real ** 2 + self.imaginary ** 2), 0)

    def __str__(self):
        if self.imaginary >= 0:
            return "%.2f+%.2fi" % (self.real, self.imaginary)
        return "%.2f-%.2fi" % (self.real, abs(self.imaginary))
"""


def test_rejects_builtin_complex_only_solution_for_complex_numbers_class() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    bad_code = """
import cmath
c1 = complex(input().split()[0], input().split()[1])
c2 = complex(input().split()[0], input().split()[1])
print(f"{c1+c2}")
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert contract["problem_family"] == "complex_numbers_class"
    assert contract["code_generation_mode"] == "class_stub"
    assert contract["class_stub_detected"] is True
    assert contract["class_name"] == "Complex"
    assert validation["passed"] is False
    assert "Built-in complex() only solution rejected for custom Complex class problem." in validation["errors"]
    assert validation["builtin_complex_only_rejected"] is True


def test_rejects_complex_class_missing_str_method() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    bad_code = """
class Complex:
    def __init__(self, real, imaginary):
        self.real = real
        self.imaginary = imaginary
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert "Custom Complex output formatting requires __str__." in validation["errors"]
    assert "__str__" in validation["missing_required_methods"]


def test_rejects_complex_mod_returning_plain_float() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    bad_code = """
import math

class Complex:
    def __init__(self, real, imaginary):
        self.real = real
        self.imaginary = imaginary

    def __add__(self, other):
        return Complex(self.real + other.real, self.imaginary + other.imaginary)

    def __sub__(self, other):
        return Complex(self.real - other.real, self.imaginary - other.imaginary)

    def __mul__(self, other):
        return Complex(0, 0)

    def __truediv__(self, other):
        return Complex(0, 0)

    def mod(self):
        return math.sqrt(self.real ** 2 + self.imaginary ** 2)

    def __str__(self):
        return "%.2f+%.2fi" % (self.real, self.imaginary)
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert "Complex.mod() must return a Complex value, not a plain float." in validation["errors"]


def test_rejects_complex_duplicate_input_reading_blocks() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    bad_code = f"""
{_correct_complex_class_code()}

c = map(float, input().split())
d = map(float, input().split())
x = Complex(*c)
y = Complex(*d)

c = map(float, input().split())
d = map(float, input().split())
x = Complex(*c)
y = Complex(*d)

print(x + y)
print(x - y)
print(x * y)
print(x / y)
print(x.mod())
print(y.mod())
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert "Complex runner must read exactly two input lines; duplicate input-reading blocks are rejected." in validation["errors"]


def test_rejects_complex_runner_missing_second_modulus() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    bad_code = f"""
{_correct_complex_class_code()}

c = map(float, input().split())
d = map(float, input().split())
x = Complex(*c)
y = Complex(*d)
print(x + y)
print(x - y)
print(x * y)
print(x / y)
print(x.mod())
"""
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert "Complex runner must print x+y, x-y, x*y, x/y, x.mod(), and y.mod()." in validation["errors"]


def test_rejects_complex_output_format_with_spaces() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    bad_code = _correct_complex_class_code().replace('"%.2f+%.2fi"', '"%.2f + %.2fi"')
    validation = validate_submission_code_against_contract(bad_code, contract)

    assert validation["passed"] is False
    assert "Custom Complex output must not include spaces around the sign." in validation["errors"]


def test_accepts_correct_complex_class_solution() -> None:
    contract = build_coding_input_contract(_complex_numbers_problem_text(), _complex_numbers_editor_text())
    validation = validate_submission_code_against_contract(_correct_complex_class_code(), contract)

    assert validation["passed"] is True
    assert validation["custom_class_validation_used"] is True
    assert validation["custom_class_validation_passed"] is True
    assert validation["missing_required_methods"] == []


def test_complex_numbers_sample_passes_with_class_harness() -> None:
    problem_text = _complex_numbers_problem_text()
    contract = build_coding_input_contract(problem_text, _complex_numbers_editor_text())
    sample_result = run_python_sample_tests(
        _correct_complex_class_code(),
        extract_sample_tests(problem_text),
        contract,
    )

    assert sample_result["ran"] is True
    assert sample_result["passed"] is True
    assert sample_result["actual_output"] == sample_result["expected_output"]
    assert sample_result["class_test_harness_used"] is True
    assert sample_result["class_test_harness_name"] == "Complex"


def test_python_completeness_rejects_incomplete_assignment_snippet() -> None:
    code = "c1_real, c1"
    validation = validate_python_code_completeness(code)
    contract_validation = validate_submission_code_against_contract(code, {})

    assert validation["passed"] is False
    assert (
        validation["python_syntax_valid"] is False
        or validation["incomplete_code_detected"] is True
    )
    assert contract_validation["passed"] is False


def test_python_completeness_rejects_unfinished_complex_input_section() -> None:
    code = """
class Complex:
    def __init__(self, real, imag):
        self.real = real
        self.imag = imag

# Read input

c1_real, c1
"""
    validation = validate_python_code_completeness(code)

    assert validation["passed"] is False
    assert validation["incomplete_code_detected"] is True


def test_python_completeness_rejects_unclosed_parenthesis() -> None:
    validation = validate_python_code_completeness("print(")

    assert validation["passed"] is False
    assert validation["python_syntax_valid"] is False


def test_python_completeness_accepts_valid_simple_python() -> None:
    validation = validate_python_code_completeness("x = int(input())\nprint(x)\n")

    assert validation["passed"] is True
    assert validation["python_syntax_valid"] is True
    assert validation["incomplete_code_detected"] is False


def test_python_completeness_accepts_valid_complex_class_runner() -> None:
    code = f"""
{_correct_complex_class_code()}

if __name__ == "__main__":
    c1_real, c1_imag = map(float, input().split())
    c2_real, c2_imag = map(float, input().split())
    x = Complex(c1_real, c1_imag)
    y = Complex(c2_real, c2_imag)
    print(x + y)
"""
    validation = validate_python_code_completeness(code)

    assert validation["passed"] is True
    assert validation["python_syntax_valid"] is True


def test_sample_runner_handles_unicode_input_on_windows_pipe() -> None:
    code = """
value = input().strip()
print(value)
"""
    sample_result = run_python_sample_tests(
        code,
        [{"input": "θ", "expected_output": "θ"}],
    )

    assert sample_result["ran"] is True
    assert sample_result["passed"] is True
    assert sample_result["actual_output"] == "θ"


def test_hackerrank_context_gate_hard_blocks_incomplete_context() -> None:
    context_status = {
        "hackerrank_context_ready": False,
        "missing_context_sections": [
            "problem_statement",
            "input_format",
            "output_format",
            "sample_input",
            "sample_output",
            "clean_full_problem_text",
        ],
        "full_problem_text_is_summary_only": True,
        "full_problem_text_contains_json_noise": True,
        "clean_full_problem_text_len": 42,
    }
    result = {
        "submission_ready_code": True,
        "code_validation_passed": True,
        "code_validation_errors": [],
        "sample_tests_found": 0,
        "correction_pass_used": False,
    }

    gated = apply_hackerrank_context_gate(result, context_status)

    assert gated["submission_ready_code"] is False
    assert gated["code_validation_passed"] is False
    assert gated["correction_pass_needed"] is False
    assert gated["correction_pass_used"] is False
    assert gated["correction_skip_reason"] == "context_not_ready"
    assert gated["context_readiness_hard_block_applied"] is True
    assert gated["submission_ready_block_reason"] == "Full HackerRank problem context was not captured."
    assert gated["unverified_code_warning"] == "Full HackerRank problem context was not captured."


def test_clean_extracted_problem_text_removes_embedded_analyzer_json() -> None:
    raw_text = """
You are given a string S. Your task is to print all possible permutations.
{ "is_question": true, "question_type": "coding", "question": "You are given a string S..." }
Input Format
A single line containing the string S.
"""

    cleaned = clean_extracted_problem_text(raw_text)

    assert "You are given a string S" in cleaned
    assert "Input Format" in cleaned
    assert "is_question" not in cleaned
    assert "question_type" not in cleaned


def test_complete_hackerrank_context_does_not_apply_hard_block() -> None:
    problem_text = """
HackerRank
Task
Read an integer and print it.
Input Format
A single line containing an integer n.
Output Format
Print n.
Sample Input 0
5
Sample Output 0
5
"""
    context_status = evaluate_hackerrank_context_readiness(
        platform="hackerrank",
        coding_answer_mode=True,
        problem_text=problem_text,
        input_format="A single line containing an integer n.",
        output_format="Print n.",
        sample_input="5",
        sample_output="5",
        sample_tests_found=1,
    )
    context_status = force_context_not_ready_for_json_noise(context_status, False)
    result = {
        "submission_ready_code": True,
        "code_validation_passed": True,
        "code_validation_errors": [],
        "sample_tests_found": 1,
    }

    gated = apply_hackerrank_context_gate(result, context_status)

    assert gated["hackerrank_context_ready"] is True
    assert gated["context_readiness_hard_block_applied"] is False
    assert gated["submission_ready_code"] is True
    assert gated["code_validation_passed"] is True
