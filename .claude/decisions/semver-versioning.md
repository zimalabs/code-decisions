---
name: semver-versioning
description: Use semantic versioning (semver) for all releases
date: 2026-03-27
tags: [versioning, release]
affects: [scripts/, src/decision/_version.py, pyproject.toml]
---

# Semver versioning schema

Use semantic versioning (MAJOR.MINOR.PATCH) for all releases. The bump script already validates semver format including pre-release suffixes (X.Y.Z-pre).
