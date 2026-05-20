
import json
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

def llm_parser_node(state, llm):
    """사용자 질문을 분석하여 JSON으로 파싱합니다."""
    prompt = state['user_query']
    
    parser_prompt_template = """You are a master of parsing user queries for a game recommendation system. Your task is to analyze the user's request and convert it into a specific JSON format.

The JSON object must have the following schema:
- `mode`: One of three values: "similar", "vibe", or "hybrid".
- `games`: A list of game titles mentioned by the user.
- `phrases`: A list of descriptive phrases.
- `target_tags`: A list of tag objects the user wants.
- `avoid_tags`: A list of tag names the user wants to avoid.
- `constraints`: An object for hard filters.

If the user's query is a general conversation, the JSON should be `{{"mode": "general"}}`.

Here are some examples:

---
Question: 엘든링이랑 비슷한 게임 찾아줘
JSON:
```json
{{
  "mode": "similar",
  "games": ["Elden Ring"],
  "phrases": [],
  "target_tags": [],
  "avoid_tags": [],
  "constraints": {{}}
}}
```
---
Question: 다크 판타지 분위기에, 호러는 아니었으면 좋겠어.
JSON:
```json
{{
  "mode": "vibe",
  "games": [],
  "phrases": ["dark fantasy mood"],
  "target_tags": [{{"name": "Dark Fantasy", "weight": 1.0}}],
  "avoid_tags": ["horror"],
  "constraints": {{}}
}}
```
---
Question: 발더스 게이트 3 같은데, 좀 더 밝은 분위기 없을까? 한국어도 지원해야 하고.
JSON:
```json
{{
  "mode": "hybrid",
  "games": ["Baldur's Gate 3"],
  "phrases": ["a brighter mood"],
  "target_tags": [],
  "avoid_tags": [],
  "constraints": {{
    "languages": ["ko"]
  }},
  "weights": {{
    "similar_weight": 0.7,
    "vibe_weight": 0.3
  }}
}}
```
---

Question: {question}
JSON:
"""
    parser_prompt = PromptTemplate.from_template(parser_prompt_template)
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
        # Handle cases where the extracted string is still not valid JSON
        print(f"Failed to parse JSON: {e}")
        # Fallback or error state
        parsed_json = {"mode": "general"}

    state['parsed_json'] = parsed_json
    return state
