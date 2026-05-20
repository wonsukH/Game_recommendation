import sys
from pathlib import Path

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils.prompts import load_prompt  # noqa: E402


def generate_response_node(state, llm):
    """최종 추천 목록과 근거 데이터를 바탕으로 자연어 응답을 생성합니다."""
    user_query = state['user_query']
    reranked_results = state['final_results'] # 이제 DataFrame을 받음

    if reranked_results.empty:
        response_text = "아쉽지만, 조건에 맞는 게임을 찾지 못했어요. 다른 조건으로 질문해주시겠어요?"
    else:
        context = ""
        for idx, row in reranked_results.iterrows():
            context += f"- Game: {row['game_title']}\n"
            context += f"  - Matched Score (0-1): {row['tag_match_score']:.2f}\n"
            context += f"---\n"

        response_prompt = PromptTemplate(
            template=load_prompt("response_generator"),
            input_variables=["user_query", "context"],
        )
        response_chain = LLMChain(llm=llm, prompt=response_prompt)
        
        response_text = response_chain.run({"user_query": user_query, "context": context})

    state['final_results'] = response_text
    return state
