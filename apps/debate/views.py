@csrf_exempt
@require_http_methods(["POST"])
def debate_summary(request, room_id: str):
    try:
        logger.info(f"[DebateSummary] START - room_id={room_id}")
        
        # Request body 파싱
        data = parse_json_body(request)
        topic = (data.get("topic") or "").strip()
        
        if not topic:
            logger.warning(f"[DebateSummary] FAILED - room_id={room_id}, reason=missing_topic")
            return JsonResponse({"error": "Missing topic"}, status=400, json_dumps_params={"ensure_ascii": False})
        
        logger.info(f"[DebateSummary] Topic received - room_id={room_id}, topic={topic[:50]}...")

        # Redis에서 토론 메시지 읽기
        logger.debug(f"[DebateSummary] Loading messages from Redis - room_id={room_id}")
        messages = load_debate_messages(room_id)
        
        if not messages:
            logger.warning(f"[DebateSummary] FAILED - room_id={room_id}, reason=no_messages_in_redis")
            return JsonResponse(
                {"error": "No debate messages in Redis"},
                status=404,
                json_dumps_params={"ensure_ascii": False}
            )
        
        logger.info(f"[DebateSummary] Messages loaded - room_id={room_id}, total_count={len(messages)}")

        # 메시지 필터링 및 변환
        debate_messages_str, used_count = build_debate_messages_json_lines(messages)
        
        if used_count == 0:
            logger.warning(f"[DebateSummary] FAILED - room_id={room_id}, reason=no_usable_messages, total_count={len(messages)}")
            return JsonResponse(
                {"error": "No usable CHAT messages (all filtered)"},
                status=404,
                json_dumps_params={"ensure_ascii": False}
            )
        
        logger.info(f"[DebateSummary] Messages filtered - room_id={room_id}, total={len(messages)}, used={used_count}, filtered_out={len(messages)-used_count}")

        # Bedrock Prompt ARN 확인
        prompt_arn = os.getenv("AWS_BEDROCK_DEBATE_SUMMARY_PROMPT_ARN")
        if not prompt_arn:
            logger.error(f"[DebateSummary] FAILED - room_id={room_id}, reason=prompt_arn_not_configured")
            return JsonResponse(
                {"error": "AWS_BEDROCK_DEBATE_SUMMARY_PROMPT_ARN not configured"},
                status=500,
                json_dumps_params={"ensure_ascii": False}
            )

        # Bedrock 프롬프트에 들어갈 변수
        prompt_variables = {
            "topic": topic,
            "debate_messages": debate_messages_str,
        }

        logger.info(f"[DebateSummary] Invoking Bedrock - room_id={room_id}, topic={topic}, used_count={used_count}, prompt_arn={prompt_arn}")
        
        # Bedrock 호출
        invoke_start = time.time()
        text = invoke_bedrock_prompt(prompt_arn, prompt_variables)
        invoke_duration = time.time() - invoke_start
        
        logger.info(f"[DebateSummary] Bedrock response received - room_id={room_id}, duration={invoke_duration:.2f}s, response_length={len(text)}")

        # 응답 파싱 시도
        try:
            parsed = json.loads(text)
            logger.info(f"[DebateSummary] SUCCESS - room_id={room_id}, response_type=json, keys={list(parsed.keys())}")
            return JsonResponse(
                {
                    "room_id": room_id,
                    "topic": topic,
                    "used_message_count": used_count,
                    "result": parsed,
                },
                json_dumps_params={"ensure_ascii": False},
                status=200,
            )
        except Exception as parse_error:
            logger.warning(f"[DebateSummary] JSON parse failed - room_id={room_id}, error={str(parse_error)}, returning raw text")
            logger.debug(f"[DebateSummary] Raw response preview - room_id={room_id}, text={text[:200]}...")
            return JsonResponse(
                {
                    "room_id": room_id,
                    "topic": topic,
                    "used_message_count": used_count,
                    "text": text,
                },
                json_dumps_params={"ensure_ascii": False},
                status=200,
            )

    except Exception as e:
        logger.error(f"[DebateSummary] ERROR - room_id={room_id}, error={str(e)}", exc_info=True)
        return JsonResponse(
            {"error": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )