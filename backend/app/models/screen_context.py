"""Version 1 transport for the main-owned Screen context (never persisted)."""
from typing import Annotated, Literal
from copy import deepcopy
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer
from pydantic_core import PydanticCustomError

Id = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Text = Annotated[str, Field(min_length=1, max_length=24000)]
Detail = Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]
MAX_METADATA_BYTES = 256 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES_BYTES = 24 * 1024 * 1024
MAX_BODY_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 2200 * 2200
MAX_OUTPUT_BYTES = 64 * 1024
MAX_PREPARED_BYTES = 32 * 1024 * 1024

# Shared by the provider schema, semantic validators, response adapter and tests.
# complete=None forbids evidence; text limits count Unicode code points, byte caps are separate.
OUTCOME_RULES = {
    "answered": dict(complete=True, items=True, missing=False, clarify=False, conflicts=False),
    "reference_accepted": dict(complete=False, items=False, missing=False, clarify=False, conflicts=False),
    "needs_more_content": dict(complete=False, items=False, missing=True, clarify=False, conflicts=False),
    "needs_clarification": dict(complete=None, items=False, missing=False, clarify=True, conflicts=True),
    "failed": dict(complete=None, items=False, missing=False, clarify=False, conflicts=False),
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ScreenIdentity(StrictModel):
    runtimeSessionId: Id
    generation: int = Field(ge=0, le=2**53 - 1)
    accountGeneration: int | None = Field(ge=0, le=2**53 - 1)
    cloudSessionId: Id | None
    threadId: Id
    turnId: Id
    operationId: Id
    requestId: Id
    baseRevision: int = Field(ge=0, le=2**53 - 1)

    @model_validator(mode="after")
    def cloud_id(self):
        if self.cloudSessionId is not None:
            UUID(self.cloudSessionId)
            if self.accountGeneration is None:
                raise ValueError("Cloud requests require account generation")
        return self


class SourceEvidence(StrictModel):
    text: Text
    complete: bool
    imageHash: Hash
    turnId: Id
    kind: Literal["reference", "question"] | None = None  # Legacy v1 callers may omit provenance.
    imageHashes: list[Hash] = Field(default_factory=list, max_length=6)
    replacesTurnIds: list[Id] = Field(default_factory=list, max_length=32)


class PreviousAnswer(StrictModel):
    text: Text
    turnId: Id


class ImageManifestItem(StrictModel):
    imageHash: Hash
    role: Literal["prior", "current", "prior_current"]
    part: Annotated[str, Field(pattern=r"^image_[0-5]$")]


class ClarificationResponse(StrictModel):
    requestId: Id
    threadId: Id
    turnId: Id
    text: Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


class ContextInput(StrictModel):
    images: list[ImageManifestItem] = Field(min_length=1, max_length=6)
    currentImageHash: Hash
    evidence: list[SourceEvidence] = Field(max_length=32)
    answers: list[PreviousAnswer] = Field(max_length=32)
    clarifications: list[ClarificationResponse] = Field(default_factory=list, max_length=32)


class PriorItem(StrictModel):
    questionId: Annotated[str, Field(min_length=1, max_length=164)]
    turnId: Id
    index: int = Field(ge=1, le=20)


class ScreenContextRequest(StrictModel):
    contractVersion: Literal["1"]
    sourceType: Literal["screen_capture"]
    identity: ScreenIdentity
    action: Literal["new", "reference", "continue"]
    contextKind: Literal["question", "reference"] = "question"
    input: ContextInput
    targetQuestionId: Annotated[str, Field(min_length=1, max_length=164)] | None = None
    priorItems: list[PriorItem] = Field(default_factory=list, max_length=20)
    replacesTurnIds: list[Id] = Field(default_factory=list, max_length=32)
    clarificationResponse: ClarificationResponse | None = None

    @model_validator(mode="after")
    def references(self):
        reply = self.clarificationResponse
        if reply and (reply.threadId != self.identity.threadId or reply.turnId != self.identity.turnId or reply.requestId == self.identity.requestId):
            raise ValueError("Clarification must reference the retained turn and previous attempt")
        if self.action == "reference" and self.contextKind != "reference":
            raise ValueError("Reference capture requires reference context")
        if self.action == "new" and self.contextKind != "question":
            raise ValueError("New question requires question context")
        data = self.input
        hashes = [item.imageHash for item in data.images]
        turns = [item.turnId for item in data.evidence]
        answer_turns = [item.turnId for item in data.answers]
        if len(set(hashes)) != len(hashes) or len({item.part for item in data.images}) != len(data.images):
            raise ValueError("Image manifest must be unique")
        if [item.part for item in data.images] != [f"image_{i}" for i in range(len(data.images))]:
            raise ValueError("Image manifest order is invalid")
        if len(set(turns)) != len(turns) or len(set(answer_turns)) != len(answer_turns):
            raise ValueError("Duplicate logical turn")
        if self.identity.turnId in turns or not set(answer_turns) <= set(turns):
            raise ValueError("Prior turn reference is invalid")
        if answer_turns != [turn for turn in turns if turn in set(answer_turns)]:
            raise ValueError("Prior answers must be chronological")
        seen_turns, seen_hashes = set(), set()
        reference_turns = []
        for item in data.evidence:
            seen_hashes.add(item.imageHash)
            if item.imageHashes and (item.imageHash not in item.imageHashes or len(set(item.imageHashes)) != len(item.imageHashes) or not set(item.imageHashes) <= seen_hashes):
                raise ValueError("Invalid supporting image provenance")
            if len(set(item.replacesTurnIds)) != len(item.replacesTurnIds) or not set(item.replacesTurnIds) <= seen_turns:
                raise ValueError("Invalid source replacement provenance")
            if item.kind == "reference":
                reference_turns.append(item.turnId)
                if self.contextKind != "reference" or item.turnId in answer_turns:
                    raise ValueError("Invalid reference identity")
            seen_turns.add(item.turnId)
        if len(reference_turns) > 1:
            raise ValueError("Multiple reference roots")
        replies = data.clarifications
        if len({reply.turnId for reply in replies}) != len(replies) or any(
                reply.turnId not in seen_turns or reply.threadId != self.identity.threadId or reply.requestId == self.identity.requestId for reply in replies):
            raise ValueError("Invalid accepted clarification provenance")
        prior_hashes = {item.imageHash for item in data.evidence}
        if set(hashes) != prior_hashes | {data.currentImageHash}:
            raise ValueError("Image reference is invalid")
        for item in data.images:
            expected = "prior_current" if item.imageHash in prior_hashes else "current"
            if item.imageHash != data.currentImageHash:
                expected = "prior"
            if item.role != expected:
                raise ValueError("Current/prior image role is invalid")
        # Map order follows first accepted use, with a distinct new capture last.
        if list(dict.fromkeys([item.imageHash for item in data.evidence] + [data.currentImageHash])) != hashes:
            raise ValueError("Image chronology is invalid")
        if self.action in {"new", "reference"}:
            if data.evidence or data.answers or data.clarifications or self.priorItems or self.replacesTurnIds or self.targetQuestionId or self.identity.baseRevision:
                raise ValueError("New question cannot inherit context")
        elif not data.evidence or self.identity.baseRevision != len(data.evidence):
            raise ValueError("Continuation requires accepted context at its revision")
        item_ids = [item.questionId for item in self.priorItems]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Duplicate prior item")
        for item in self.priorItems:
            if item.turnId not in answer_turns or item.questionId != f"{item.turnId}:{item.index}":
                raise ValueError("Invalid prior question identity")
        if self.targetQuestionId is not None and self.targetQuestionId not in item_ids:
            raise ValueError("Unknown continuation target")
        if len(set(self.replacesTurnIds)) != len(self.replacesTurnIds) or not set(self.replacesTurnIds) <= set(turns):
            raise ValueError("Invalid explicit replacement")
        if any(not item.text.strip() for item in [*data.evidence, *data.answers]):
            raise ValueError("Empty prior content")
        return self


class EvidenceDelta(StrictModel):
    text: Text
    complete: bool
    imageHashes: list[Hash] = Field(min_length=1, max_length=6)
    replacesTurnIds: list[Id] = Field(max_length=32)


class AnswerItem(StrictModel):
    index: int = Field(ge=1, le=20)
    display_number: Annotated[str, Field(max_length=32)]
    question: Annotated[str, Field(min_length=1, max_length=8000)]
    question_type: Literal["coding", "mcq", "visual", "debugging", "output", "interview", "architecture", "general"]
    answer: Text
    language: Annotated[str, Field(max_length=64)]
    code: Annotated[str, Field(max_length=24000)]


class ScreenContextOutput(StrictModel):
    outcome: Literal["answered", "reference_accepted", "needs_more_content", "needs_clarification", "failed"]
    evidenceDelta: EvidenceDelta | None
    items: list[AnswerItem] = Field(max_length=20)
    missingDetails: list[Detail] = Field(max_length=20)
    conflicts: list[Detail] = Field(max_length=20)
    clarification: Detail | None

    @model_validator(mode="after")
    def combinations(self):
        # Static codes identify cross-field failures without logging source values or messages.
        def require(condition, code):
            if not condition:
                raise PydanticCustomError("screen_output_" + code, "Invalid Screen output")

        rule = OUTCOME_RULES[self.outcome]
        source = rule["complete"] is not None
        answered = rule["items"]
        clarify = rule["clarify"]
        require((self.evidenceDelta is not None) == source, "evidence_presence")
        if self.evidenceDelta is not None:
            require(self.evidenceDelta.complete == rule["complete"], "evidence_complete")
            require(bool(self.evidenceDelta.text.strip()), "evidence_blank")
        require(bool(self.items) == answered, "items_presence")
        require(bool(self.missingDetails) == rule["missing"], "missing_details_presence")
        require(rule["conflicts"] or not self.conflicts, "conflicts_forbidden")
        require((self.clarification is not None) == clarify, "clarification_presence")
        require(all(item.question.strip() for item in self.items), "question_blank")
        require(all(item.answer.strip() for item in self.items), "answer_blank")
        require([item.index for item in self.items] == list(range(1, len(self.items) + 1)), "item_order")
        require(all(item.question_type != "coding" or item.code.strip() for item in self.items), "coding_code_missing")
        require(all(item.question_type != "coding" or item.language.strip() for item in self.items), "coding_language_missing")
        return self


class ScreenContextProviderOutput(StrictModel):
    # OpenAI requires an object root; outcome-specific alternatives live inside it.
    result: ScreenContextOutput

    @classmethod
    def schema_for_action(cls, action):
        schema = cls.model_json_schema()
        canonical = schema["$defs"]["ScreenContextOutput"]
        evidence = schema["$defs"]["EvidenceDelta"]
        outcomes = (["reference_accepted", "needs_clarification", "failed"] if action == "reference"
                    else ["answered", "needs_more_content", "needs_clarification", "failed"])
        branches = []
        for outcome in outcomes:
            rule = OUTCOME_RULES[outcome]
            branch = deepcopy(canonical)
            props = branch["properties"]
            props["outcome"] = {"type": "string", "enum": [outcome]}
            source = rule["complete"] is not None
            if source:
                props["evidenceDelta"] = deepcopy(evidence)
                props["evidenceDelta"]["properties"]["complete"] = {"type": "boolean", "enum": [rule["complete"]]}
            else:
                props["evidenceDelta"] = {"type": "null"}
            for field, required in (("items", rule["items"]), ("missingDetails", rule["missing"])):
                props[field]["minItems" if required else "maxItems"] = 1 if required else 0
            if not rule["clarify"]:
                props["conflicts"]["maxItems"] = 0
                props["clarification"] = {"type": "null"}
            else:
                props["clarification"] = deepcopy(props["clarification"]["anyOf"][0])
            branches.append(branch)
        schema["properties"]["result"] = {"anyOf": branches}
        return schema

class ControllerEvidence(StrictModel):
    text: Text
    complete: bool


class ControllerResult(StrictModel):
    validated: Literal[True]
    evidence: ControllerEvidence
    answer: Text | None = None

    @model_serializer(mode="wrap")
    def omit_absent_answer(self, handler):
        data = handler(self)
        if self.answer is None:
            data.pop("answer", None)  # Phase 1 evidence-only commits require the key to be absent.
        return data


class ResultItem(AnswerItem):
    question_id: Annotated[str, Field(min_length=1, max_length=164)]


class ContextMetrics(StrictModel):
    logicalScreenCalls: int = Field(ge=0, le=1)
    httpAttempts: int = Field(ge=0, le=1)
    sdkMaxRetries: Literal[0] = 0
    imagesSupplied: int = Field(ge=1, le=6)
    newCaptureCount: Literal[1] = 1


class ScreenContextResponse(StrictModel):
    contractVersion: Literal["1"] = "1"
    identity: ScreenIdentity
    outcome: Literal["answered", "reference_accepted", "needs_more_content", "needs_clarification", "failed"]
    committable: bool
    controllerResult: ControllerResult | None
    evidenceDelta: EvidenceDelta | None
    answer: Annotated[str, Field(max_length=24000)]
    items: list[ResultItem] = Field(max_length=20)
    missingDetails: list[Detail] = Field(max_length=20)
    conflicts: list[Detail] = Field(max_length=20)
    clarification: Detail | None
    errorCode: Literal["provider_unavailable", "provider_error", "provider_timeout", "provider_rate_limited", "provider_configuration", "provider_refused", "incomplete_output", "invalid_output", "output_limit"] | None
    metrics: ContextMetrics

    @model_validator(mode="after")
    def outcome_contract(self):
        ScreenContextOutput(outcome=self.outcome, evidenceDelta=self.evidenceDelta,
                            items=[AnswerItem.model_validate(item.model_dump(exclude={"question_id"})) for item in self.items],
                            missingDetails=self.missingDetails, conflicts=self.conflicts, clarification=self.clarification)
        committable = OUTCOME_RULES[self.outcome]["complete"] is not None
        valid = self.committable == committable and (self.errorCode is None or self.outcome == "failed")
        if committable:
            result = self.controllerResult
            valid = valid and result is not None and result.evidence.text == self.evidenceDelta.text and result.evidence.complete == self.evidenceDelta.complete
            if self.outcome == "answered":
                valid = valid and bool(self.answer.strip()) and result.answer == self.answer
            else:
                valid = valid and not self.answer and result.answer is None
        else:
            valid = valid and self.controllerResult is None and not self.answer
        if not valid:
            raise PydanticCustomError("screen_response_commit_contract", "Invalid Screen commit contract")
        return self
