#!/usr/bin/env python3
"""Read-only pre-send byte-identity gate. Never sends or uploads."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REFERENCE = Path.home() / ('Downloads/Alex_Mercer_Resume_Generic_AI_Product_Manager_Aligned_Emoj.pdf')
APPROVED_SHA256 = '0226493902e35799cc5fbb5587add7ba355c7046ebe42e513e2567649da8633e'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resume', help='Exact file selected for sending or uploading')
    parser.add_argument('--approval-receipt', help='Explicit exact-artifact user approval, scoped to one target')
    parser.add_argument('--target', help='Exact approved recipient or native application source URL')
    args = parser.parse_args()
    try:
        candidate = Path(args.resume).resolve(strict=True)
        reference_hash = digest(REFERENCE)
        candidate_hash = digest(candidate)
        ok = reference_hash == APPROVED_SHA256 and candidate_hash == APPROVED_SHA256
        scoped = False
        if args.approval_receipt or args.target:
            if not args.approval_receipt or not args.target:
                raise ValueError('Both approval receipt and exact target are required')
            receipt = json.loads(Path(args.approval_receipt).read_text())
            targets = receipt.get('allowed_targets')
            if not isinstance(targets, list) or not targets or any(not isinstance(t, str) or not t or '*' in t or '\n' in t or '\r' in t for t in targets):
                raise ValueError('Invalid explicit target scope')
            scoped = (receipt.get('approval_type') == 'explicit_user_approved_exact_artifact'
                      and receipt.get('approved') is True
                      and receipt.get('approved_by') == 'Vasya'
                      and bool(receipt.get('approved_at'))
                      and bool(receipt.get('source_user_text'))
                      and receipt.get('resume_sha256') == candidate_hash
                      and Path(receipt.get('resume_path', '')).resolve(strict=True) == candidate
                      and args.target in targets)
            ok = reference_hash == APPROVED_SHA256 and scoped
        result = {'ok': ok, 'resume': str(candidate), 'reference': str(REFERENCE),
                  'expected_sha256': candidate_hash if scoped else APPROVED_SHA256, 'reference_sha256': reference_hash,
                  'resume_sha256': candidate_hash,
                  'reason': ('explicit_user_approved_exact_artifact_for_target' if scoped else 'byte_identical_approved_resume') if ok else 'BLOCKED_NON_APPROVED_RESUME'}
        if scoped:
            result.update({'approval_receipt': str(Path(args.approval_receipt).resolve()),
                           'approval_receipt_sha256': digest(args.approval_receipt), 'target': args.target})
    except Exception as exc:
        result = {'ok': False, 'reason': 'BLOCKED_UNREADABLE_RESUME', 'error': str(exc)}
    print(json.dumps(result))
    return 0 if result['ok'] else 2

if __name__ == '__main__':
    sys.exit(main())
