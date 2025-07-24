                            async def stream_anthropic_response():
                                """Simplified Anthropic streaming using parallel broadcaster"""
                                try:
                                    # Create parallel broadcaster for handling multiple clients
                                    broadcaster = create_broadcaster(request, request_id, current_provider.name)
                                    
                                    # TODO: Add duplicate requests to broadcaster here
                                    # This would require accessing waiting duplicate requests
                                    
                                    # Check if response is an error before trying to iterate
                                    if response.status_code >= 400:
                                        debug(
                                            LogRecord(
                                                "provider_error_response",
                                                f"Provider returned error status {response.status_code}",
                                                request_id,
                                                {
                                                    "provider": current_provider.name,
                                                    "status_code": response.status_code
                                                }
                                            )
                                        )
                                        return
                                    
                                    # Create provider stream from response
                                    async def provider_stream():
                                        try:
                                            async for chunk in response.aiter_text():
                                                collected_chunks.append(chunk)
                                                yield chunk
                                        except Exception as e:
                                            error(
                                                LogRecord(
                                                    "provider_stream_error",
                                                    f"Error in provider stream: {type(e).__name__}: {e}",
                                                    request_id,
                                                    {
                                                        "provider": current_provider.name,
                                                        "error": str(e)
                                                    }
                                                )
                                            )
                                            raise
                                    
                                    # Use broadcaster to handle parallel streaming with disconnect detection
                                    async for chunk in broadcaster.stream_from_provider(provider_stream()):
                                        yield chunk
                                        
                                except Exception as e:
                                    error(
                                        LogRecord(
                                            "stream_anthropic_error",
                                            f"Error in Anthropic streaming: {type(e).__name__}: {e}",
                                            request_id,
                                            {
                                                "provider": current_provider.name,
                                                "error": str(e)
                                            }
                                        )
                                    )
                                    raise
                                finally:
                                    # Complete and cleanup request with collected chunks
                                    complete_and_cleanup_request(signature, None, collected_chunks, True, current_provider.name)