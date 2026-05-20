
import sys
import json
from pathlib import Path

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils.prompts import load_prompt  # noqa: E402
from utils.logging import get_logger  # noqa: E402

log = get_logger("rag.parser")


def llm_parser_node(state, llm):
    """사용자 질문을 분석하여 JSON으로 파싱합니다."""
    prompt = state['user_query']

    parser_prompt = PromptTemplate.from_template(load_prompt("parser"))
    # LangChain Expression Language (LCEL) 사용
    parser_chain = parser_prompt | llm
    
    result = parser_chain.invoke({"question": prompt})
    result_str = result.content
    
    try:
        # Find the start and end of the JSON object
        start_index = result_str.find('{')
        end_index = result_str.rfind('}')
        
        if start_index != -1 and end_index != -1:
            json_str = result_str[start_index:end_index+1]
            parsed_json = json.loads(json_str)
        else:
            # Fallback if no JSON object is found
            parsed_json = {"mode": "general"}
            
    except json.JSONDecodeError as e:
        log.warning("LLM output was not valid JSON, falling back to mode=general: %s", e)
        parsed_json = {"mode": "general"}

    state['parsed_json'] = parsed_json
    return state
