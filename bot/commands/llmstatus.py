def format_llmstatus(up: bool, models: list, configured_model: str, breaker_state: str) -> str:
    """Pure formatter for the /llmstatus admin command's embed body.

    up/models come from rag.answer.OllamaAnswerer.check_health();
    breaker_state comes from a rag.circuit_breaker.CircuitBreaker's .state.
    """
    if up:
        status_line = "\U0001F7E2 Online"
        if models:
            loaded_note = "loaded" if configured_model in models else "NOT in the loaded models list"
            models_text = ", ".join(models)
        else:
            loaded_note = "no models reported"
            models_text = "none"
        model_line = f"**Configured model:** {configured_model} ({loaded_note})\n**Loaded models:** {models_text}\n"
    else:
        status_line = "\U0001F534 Offline"
        model_line = f"**Configured model:** {configured_model}\n"

    return f"**LLM status:** {status_line}\n{model_line}**Circuit breaker:** {breaker_state}"
