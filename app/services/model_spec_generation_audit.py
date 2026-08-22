from __future__ import annotations

_INSTALLED = False


def install_model_spec_generation_audit() -> None:
    """Remove compatibility bypasses that contradict current provider contracts."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services.generations import GenerationService

    # Older Seedance 2 docs were interpreted as permitting temporal frames plus
    # multimodal references. The current Kie forms explicitly make these modes
    # mutually exclusive. Returning an empty stash lets ModelCatalog validate the
    # user's exact request before quote/debit instead of hiding refs temporarily.
    GenerationService._seedance20_hybrid_references = staticmethod(
        lambda model_id, parameters: {}
    )
