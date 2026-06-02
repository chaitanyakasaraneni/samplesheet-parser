# Makefile for samplesheet-parser
# Keeps the version in sync across pyproject.toml, CITATION.cff, and .zenodo.json.
# Portable to GNU Make 3.81 (macOS default) — recipes are single POSIX-sh lines.

PKG       := samplesheet_parser
PYPROJECT := pyproject.toml
CITATION  := CITATION.cff
ZENODO    := .zenodo.json
CHANGELOG := CHANGELOG.md

CURRENT_VERSION := $(shell sed -n -E 's/^version = "([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' $(PYPROJECT) | head -1)

.DEFAULT_GOAL := help
.PHONY: help version major minor patch tag test lint build clean

help:
	@echo "samplesheet-parser — current version: $(CURRENT_VERSION)"
	@echo ""
	@echo "Version bumping (syncs $(PYPROJECT), $(CITATION), $(ZENODO); rolls $(CHANGELOG)):"
	@echo "  make patch    patch bump (x.y.Z)"
	@echo "  make minor    minor bump (x.Y.0)"
	@echo "  make major    major bump (X.0.0)"
	@echo ""
	@echo "Other targets:"
	@echo "  make version  print the current version"
	@echo "  make tag      create git tag v$(CURRENT_VERSION)"
	@echo "  make test     run pytest"
	@echo "  make lint     run ruff"
	@echo "  make build    build sdist + wheel"
	@echo "  make clean    remove build artifacts"

version:
	@echo $(CURRENT_VERSION)

patch minor major:
	@$(MAKE) --no-print-directory _bump PART=$@

# internal: bump the version part named by PART across all files (one shell line)
_bump:
	@cur="$(CURRENT_VERSION)"; \
	[ -n "$$cur" ] || { echo "error: could not read version from $(PYPROJECT)"; exit 1; }; \
	MA=$${cur%%.*}; rest=$${cur#*.}; MI=$${rest%%.*}; PA=$${rest##*.}; \
	case "$(PART)" in \
	  major) MA=$$((MA + 1)); MI=0; PA=0 ;; \
	  minor) MI=$$((MI + 1)); PA=0 ;; \
	  patch) PA=$$((PA + 1)) ;; \
	  *) echo "error: unknown bump part '$(PART)'"; exit 1 ;; \
	esac; \
	new="$$MA.$$MI.$$PA"; today="$$(date +%F)"; \
	sed -E 's/^version = "[0-9]+\.[0-9]+\.[0-9]+"/version = "'"$$new"'"/' $(PYPROJECT) > $(PYPROJECT).tmp && mv $(PYPROJECT).tmp $(PYPROJECT); \
	sed -E -e 's/^version: .*/version: '"$$new"'/' -e 's/^date-released: .*/date-released: '"$$today"'/' $(CITATION) > $(CITATION).tmp && mv $(CITATION).tmp $(CITATION); \
	sed -E 's/("version": )"[0-9]+\.[0-9]+\.[0-9]+"/\1"'"$$new"'"/' $(ZENODO) > $(ZENODO).tmp && mv $(ZENODO).tmp $(ZENODO); \
	cl_note=""; \
	if [ -f $(CHANGELOG) ] && grep -q '^## \[Unreleased\]' $(CHANGELOG); then \
	  awk -v v="$$new" -v d="$$today" '!done && /^## \[Unreleased\]/ {print "## [Unreleased]"; print ""; print "_No unreleased changes._"; print ""; print "## [" v "] - " d; done=1; next} {print}' $(CHANGELOG) > $(CHANGELOG).tmp && mv $(CHANGELOG).tmp $(CHANGELOG); \
	  cl_note=", $(CHANGELOG)"; \
	else \
	  cl_note=" (warning: no [Unreleased] section in $(CHANGELOG) — not rolled)"; \
	fi; \
	echo "Bumped $$cur -> $$new  (date-released: $$today)"; \
	echo "  updated: $(PYPROJECT), $(CITATION), $(ZENODO)$$cl_note"; \
	echo "Next: review $(CHANGELOG), then: git commit -am \"release v$$new\" && make tag && git push --follow-tags"

tag:
	@v="$(CURRENT_VERSION)"; \
	if git rev-parse "v$$v" >/dev/null 2>&1; then echo "tag v$$v already exists"; exit 1; fi; \
	git tag -a "v$$v" -m "Release v$$v"; \
	echo "created annotated tag v$$v  (push with: git push --follow-tags)"

test:
	@pytest

lint:
	@ruff check $(PKG)/

build:
	@python3 -m hatchling build

clean:
	@rm -rf dist build *.egg-info
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +
