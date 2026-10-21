"""Offline blinded review packs. Reads synthetic samples; never calls a provider.

Baseline/candidate JSON: revision, sample_origin (provider_generated or
authored_fixture), samples [{case_id, answer, model, profile, settings,
input_sha256, attempt_role, sample_index}]. No missing outputs are reconstructed.
The reviewer pack omits revision/model/version mapping; keep key.json separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from answer_quality_spec import CASES

DIMENSIONS = ('correctness', 'relevance', 'clarity', 'useful_depth', 'specificity',
              'naturalness', 'structure', 'grounding', 'repetition')


def input_hash(case):
    data = {key: case[key] for key in ('question', 'evidence', 'history')}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def review_pack(baseline, candidate, seed):
    cases = {case['id']: case for case in CASES}
    def index(run):
        if not run.get('revision') or run.get('sample_origin') not in ('provider_generated', 'authored_fixture'):
            raise ValueError('Explicit revision and sample provenance required')
        records = {}
        for item in run['samples']:
            case = cases[item['case_id']]
            if not isinstance(item['answer'], str) or not item['answer'].strip():
                raise ValueError('Missing output; never manufacture a baseline')
            if item['input_sha256'] != input_hash(case):
                raise ValueError('Synthetic input mismatch')
            if not isinstance(item['settings'], dict) or not item['model'] or not item['profile']:
                raise ValueError('Model/profile/settings required')
            if item['attempt_role'] not in ('primary', 'fallback') or type(item['sample_index']) is not int:
                raise ValueError('Attempt role/sample index required')
            key = (item['case_id'], item['attempt_role'], item['sample_index'])
            if key in records:
                raise ValueError('Duplicate sample identity')
            records[key] = item
        return records
    before, after = index(baseline), index(candidate)
    if not before or before.keys() != after.keys() or baseline['sample_origin'] != candidate['sample_origin']:
        raise ValueError('Paired sample identities and provenance must match')
    rng = random.Random(seed)
    order = sorted(before)
    rng.shuffle(order)
    pack, key = [], []
    for number, identity in enumerate(order, 1):
        left, right = before[identity], after[identity]
        if any(left[name] != right[name] for name in ('model', 'profile', 'settings', 'input_sha256')):
            raise ValueError('Paired model/profile/settings/input must match')
        swapped = bool(rng.getrandbits(1))
        case = cases[identity[0]]
        pack.append(dict(review_id=number, question=case['question'], question_type=case['expected_intent'],
            evidence=case['evidence'], history=case['history'], permitted_personal_facts=case['permitted_personal_facts'],
            prohibited_inferences=case['prohibited_inferences'], essential_content=case['essential_content'],
            critical_failures=case['critical_failures'], A=(right if swapped else left)['answer'],
            B=(left if swapped else right)['answer'],
            scores={side: dict.fromkeys(DIMENSIONS) for side in ('A', 'B')},
            critical_failure={'A': None, 'B': None}, preference=None, review_notes=''))
        key.append(dict(review_id=number, case_id=identity[0], attempt_role=identity[1], sample_index=identity[2],
                        A='candidate' if swapped else 'baseline', B='baseline' if swapped else 'candidate'))
    disclosure = dict(sample_origin=baseline['sample_origin'],
                      measured_model_outputs=baseline['sample_origin'] == 'provider_generated')
    return dict(**disclosure, reviews=pack), dict(seed=seed, baseline_revision=baseline['revision'],
        candidate_revision=candidate['revision'], model_settings=[dict(case_id=i[0], model=before[i]['model'],
            profile=before[i]['profile'], settings=before[i]['settings']) for i in order], assignments=key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=20261021)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pack, key = review_pack(json.loads(args.baseline.read_text(encoding='utf-8')),
                            json.loads(args.candidate.read_text(encoding='utf-8')), args.seed)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in [('review.json', pack), ('key.json', key)]:
        (args.output / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(paired_cases=len(pack['reviews']), sample_origin=pack['sample_origin'], provider_calls=0)))


if __name__ == '__main__':
    main()
