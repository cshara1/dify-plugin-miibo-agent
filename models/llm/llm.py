import json
import logging
from collections.abc import Generator
from typing import Iterator, Optional, Union, cast

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
)
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.llm.errors import (
    InvalidAuthenticationError,InvalidAPIKeyError,RateLimitReachedError,InsufficientAccountBalanceError,InternalServerError,BadRequestError
)
from models.llm.miibo_agent import MiiboAgent

logger = logging.getLogger(__name__)


class MiiboLanguageModel(LargeLanguageModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        return self._generate(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stream=stream,
            user=user,
        )

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return 0 # self._num_tokens_from_messages(prompt_messages)


    def validate_credentials(self, model: str, credentials: dict) -> None:
        # ping
        instance = MiiboAgent(api_key=credentials["api_key"], agent_id=credentials["agent_id"])

        try:
            instance.generate(
                model=model,
                stream=False,
                messages=[],
                parameters={
                    "max_tokens": 1,
                },
                timeout=60,
            )
        except Exception as e:
            raise CredentialsValidateFailedError(f"Invalid API key: {e}")

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dict for Baichuan
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            else:
                message_dict = {"role": "user"}
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_dict['content'] = message_content.data
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_dict['image'] = message_content.base64_data
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                message_dict["tool_calls"] = [tool_call.dict() for tool_call in message.tool_calls]
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {"role": "tool", "content": message.content, "tool_call_id": message.tool_call_id}
        else:
            raise ValueError(f"Unknown message type {type(message)}")

        return message_dict

    def _generate(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        user: str,
        tools: list[PromptMessageTool] | None = None,
        stream: bool = False,
    ) -> LLMResult | Generator:
        instance = MiiboAgent(api_key=credentials["api_key"], agent_id=credentials["agent_id"])
        messages = [self._convert_prompt_message_to_dict(m) for m in prompt_messages]

        # invoke model
        response = instance.generate(
            model=model,
            stream=stream,
            user= user,
            messages=messages,
            parameters=model_parameters,
            timeout=60,
            tools=tools,
        )

        if stream:
            return self._handle_chat_generate_stream_response(model, prompt_messages, credentials, response)

        return self._handle_chat_generate_response(model, prompt_messages, credentials, response)

    def _handle_chat_generate_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: dict,
    ) -> LLMResult:
        answer = response.get("bestResponse")
        assistant_message = AssistantPromptMessage(content=answer['utterance'], tool_calls=[])
        usage = LLMUsage.empty_usage()
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_message,
            usage=usage,
        )

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Iterator,
    ) -> Generator:
        for line in response:
            if not line:
                continue
            line = line.decode("utf-8")
            try:
                data = json.loads(line)
            except Exception as e:
                raise InternalServerError(f"Failed to convert response to json: {e} with text: {line}")
            
            if 'bestResponse' in data:
                answer = data.get("bestResponse", {})

                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=answer['utterance'], tool_calls=[]),
                        finish_reason="",
                    ),
                )

            if 'utterance' in data:
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content="", tool_calls=[]),
                        usage=LLMUsage.empty_usage(),
                        finish_reason="finished",
                    ),
                )

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [],
            InvokeServerUnavailableError: [InternalServerError],
            InvokeRateLimitError: [RateLimitReachedError],
            InvokeAuthorizationError: [
                InvalidAuthenticationError,
                InsufficientAccountBalanceError,
                InvalidAPIKeyError,
            ],
            InvokeBadRequestError: [BadRequestError, KeyError],
        }
