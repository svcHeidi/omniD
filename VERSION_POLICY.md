# Version Policy

omniD is a monorepo of independently versioned packages: `omnidriver` (core orchestrator) and plugins (`omnidriver-openfoam`, `omnidriver-cardiacfoam`, and future domain plugins such as a deal.II package). Each package strictly adheres to [Semantic Versioning 2.0.0](https://semver.org/) **on its own version number** — there is no shared/lockstep version across packages.

## Core (`omnidriver`)

Given the nature of core as a workflow orchestrator, we guarantee backward compatibility on the following components:

- **Command-line Interface (CLI)**: CLI arguments and standard exit codes.
- **Schemas**: The structural schema of `run-document.json`.
- **Plugin API**: The interface expected by `omnidriver.plugins` entry points.

Any breaking changes to the above result in a major version bump on `omnidriver`. Internal Python modules not explicitly exposed as part of the public API may change in minor versions.

## Plugins (`omnidriver-openfoam`, `omnidriver-cardiacfoam`, ...)

Plugins are agnostic to each other: a plugin depends on `omnidriver` core (and, only where it genuinely needs to, on another specific plugin — e.g. `omnidriver-cardiacfoam` depends on `omnidriver-openfoam`), never on siblings it doesn't use. A new plugin that only needs core (e.g. a future deal.II plugin) depends on `omnidriver` alone.

Each plugin pins its `omnidriver` (and any plugin) dependency with a PEP 440 compatible-release specifier against the current 0.x line, e.g. `omnidriver~=0.1.0`. This means:

- A patch release of core (`0.1.0` → `0.1.1`) reaches plugins automatically — no plugin release needed.
- A minor release of core (`0.1.x` → `0.2.0`) is treated as potentially interface-breaking while core is pre-1.0, so it does **not** flow to plugins automatically — a plugin only picks it up when its own pin is deliberately widened (a maintainer decision, made when the plugin actually adopts whatever changed).

Once core reaches `1.0.0`, its Plugin API guarantees above make minor releases safe to consume automatically, so plugin pins can widen to `omnidriver>=1.0,<2`.

## Releasing

Each package is tagged and released independently: `<package-dir>-v<version>`, e.g. `omnidriver-v0.1.0`, `omnidriver-openfoam-v0.2.3`. Pushing such a tag triggers [.github/workflows/release.yml](.github/workflows/release.yml), which builds the sdist/wheel for that package and attaches them to a GitHub Release — the tagged version must match the `version` already committed in that package's `pyproject.toml`.

There is no public or private package index yet. Install a specific release with:

```bash
pip install "omnidriver-cardiacfoam @ git+https://github.com/svcHeidi/omniD.git@omnidriver-cardiacfoam-v0.1.0#subdirectory=packages/omnidriver-cardiacfoam"
```

This is intentional while the cardiac (and any future clinical/domain-specific) plugin should stay out of a publicly discoverable index; core (`omnidriver`) may move to public PyPI on its own once there's demand for it outside this checkout.
