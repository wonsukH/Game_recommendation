from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

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

        prompt_template = """You are a helpful and friendly game recommender chatbot.
        Based on the user's query and the provided list of recommended games with their data, generate a friendly response.

        **Core Rules:**
        1. You MUST only explain and select from the games provided in the list below. Do not mention any other games.
        2. For each game, provide a concise 1-2 line explanation.
        3. Your explanation for each game should be based on its matching score (TagMatch) and key metadata (e.g., single-player support, price, Korean language support). Be persuasive.
        4. Do NOT mention any features the user wanted to avoid (e.g., if they said "no horror", do not mention horror at all). Focus only on the positive reasons for the recommendation.

        **User Query:**
        {user_query}

        **Recommended Games Data (for your reference only, do not show this data to the user):**
        {context}

        Now, generate a friendly, natural, and final response to the user in Korean:
        """
        
        response_prompt = PromptTemplate(template=prompt_template, input_variables=["user_query", "context"])
        response_chain = LLMChain(llm=llm, prompt=response_prompt)
        
        response_text = response_chain.run({"user_query": user_query, "context": context})

    state['final_results'] = response_text
    return state
