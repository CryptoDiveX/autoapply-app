.PHONY: verify-local verify-release test-python test-swift build-dmg build-dev promote-production audit-privacy test-e2e

verify-local: audit-privacy test-python test-swift build-dmg test-e2e
	@echo "verify-local: PASSED (Privacy audit + Python suites + Swift runner + Universal AutoApply.app + DMG installer verified)"

audit-privacy:
	python3 ./packaging/audit_opensource_privacy.py

test-python:
	PYTHONPATH=runtime:. pytest tests/unit tests/contract tests/security tests/coexistence tests/integration

test-swift:
	swift run AutoApplyNativeTestRunner

build-dev:
	swift build -c release --arch arm64 --arch x86_64 --product AutoApply
	cp "$$(swift build -c release --arch arm64 --arch x86_64 --product AutoApply --show-bin-path)/AutoApply" /Applications/AutoApply.app/Contents/MacOS/AutoApply
	cp -R runtime/autoapply /Applications/AutoApply.app/Contents/Resources/runtime/
	codesign --force --sign - /Applications/AutoApply.app/Contents/MacOS/AutoApply
	codesign --force --sign - /Applications/AutoApply.app
	@echo "build-dev: Updated local /Applications/AutoApply.app (dev stage only — production installers untouched)"

build-dmg:
	./packaging/build_macos_installer.sh

promote-production:
	chmod +x ./packaging/promote_production_release.sh ./packaging/audit_opensource_privacy.py
	./packaging/promote_production_release.sh

test-e2e:
	PYTHONPATH=runtime:. pytest tests/e2e/test_macos_app_and_dmg_installer.py

verify-release:
	@python3 -c 'import json, pathlib, sys; \
gates = json.loads(pathlib.Path("docs/release/gates.json").read_text())["gates"]; \
unapproved = [g["id"] for g in gates if g.get("status") != "approved" or not g.get("approval_artifact")]; \
sys.exit(f"verify-release: BLOCKED — unapproved release gates: {unapproved}") if unapproved else print("verify-release: ALL GATES APPROVED")'
