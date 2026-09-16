# Sourcing Static Manifest Deployment Hotfix — 1.0.117

The production image uses Django `ManifestStaticFilesStorage`. Release tasks deliberately run focused application tests before mutating the shared static volume with `collectstatic`. Sourcing templates reference release-owned CSS/JS, so a Django Client test that renders those templates must not depend on the previous deployment's collected manifest.

## Failure corrected

1.0.116 correctly disabled the production HTTP→HTTPS redirect inside Sourcing HTTP tests, allowing requests to reach the views. The next production rehearsal then exposed the underlying static-manifest dependency: rendering `templates/sourcing/base.html` requested `sourcing/css/directory.css`, but the shared production manifest had not yet been rebuilt for the new release. Django raised `Missing staticfiles manifest entry`, the focused test stopped the release, and the later `collectstatic` step never ran.

## Authority boundary

1.0.117 does **not** disable production manifest storage. Production continues to use `django.contrib.staticfiles.storage.ManifestStaticFilesStorage`, and HTTPS redirect remains enabled by default. Only Sourcing HTTP tests override the staticfiles backend to `StaticFilesStorage`, so tests exercise template/view authorization without depending on a production artifact that intentionally does not exist yet.

After focused tests pass, release tasks run normal production `collectstatic --noinput`, then `verify_sourcing_static_manifest`. The latter must resolve these manifest entries before cutover:

- `sourcing/css/directory.css`
- `sourcing/js/finder-scale.js`
- `sourcing/js/manpower-directory.js`
- `sourcing/js/vendor-directory.js`

A missing entry blocks deployment before the live web container is promoted.

## Deployment expectation

Deploy 1.0.117 normally. The focused Sourcing tests should render without manifest errors. The release must then print `Sourcing static manifest verified.` after `collectstatic`. No database migration is introduced by this hotfix.
