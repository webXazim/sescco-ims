#!/usr/bin/env python3
"""Static release contract for unsaved-draft recovery across provider creates.

The browser warning/storage behavior must additionally be tested in staging.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(rel, required):
    path = ROOT / rel
    if not path.is_file():
        raise SystemExit(f"SOURCING DRAFT RECOVERY ERROR: missing {rel}")
    text = path.read_text(encoding="utf-8")
    for marker in required:
        if marker not in text:
            raise SystemExit(f"SOURCING DRAFT RECOVERY ERROR: {rel} missing {marker!r}")


for module, guard, editor in (
    ("vendors", "show_materials", "vendor-onboarding.js"),
    ("manpower", "show_capabilities", "provider-capability-onboarding.js"),
    ("subcontractors", "show_capabilities", "provider-capability-onboarding.js"),
):
    check(f"templates/sourcing/{module}/form.html", [
        "data-sourcing-draft-form", guard, "sourcing-draft-recovery.js",
        "provider-tag-editor.js", editor,
    ])

check("templates/sourcing/base.html", ["sourcing-draft-cleanup.js"])
check("static/sourcing/js/sourcing-draft-recovery.js", [
    "sessionStorage.setItem", "sessionStorage.getItem", "beforeunload",
    "event.returnValue = ''", "pagehide", "visibilitychange", "Draft restored",
    "onboarding.capture()", "onboarding.restore(", "sourcing:draft-restore",
    "submitted: submitting", "Discard draft", "maxAge", "data-sourcing-draft-form",
])
check("static/sourcing/js/sourcing-draft-cleanup.js", [
    "entry?.submitted", "entry.path !== location.pathname", "logout",
])
check("static/sourcing/js/vendor-onboarding.js", [
    "window.SourcingOnboardingDraft", "captureDraft", "restoreDraft",
    "stagedCategories?.refresh()", "sourcing:reference-lookup-restore",
])
check("static/sourcing/js/provider-capability-onboarding.js", [
    "window.SourcingOnboardingDraft", "captureDraft", "restoreDraft",
    "stagedCategories?.refresh()", "sourcing:reference-lookup-restore",
])
check("static/sourcing/js/reference-lookup.js", ["sourcing:reference-lookup-restore", "load('', selectedId)"])
check("static/sourcing/js/provider-tag-editor.js", ["sourcing:draft-restore", "field.dispatchEvent(new Event('change'"])
check("static/sourcing/css/vendor-onboarding.css", [".sourcing-draft-notice", ".sourcing-draft-notice__discard"])
print("PASS: all three create pages have scoped draft recovery, leave warning, dynamic capability restoration, tag restoration, and success/logout cleanup contracts.")
