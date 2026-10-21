from langchain_groq import ChatGroq
from BaseState import BaseState

llm = ChatGroq(model="openai/gpt-oss-120b")

def router_node(BaseState):
    systen_prompt = f""" You are the manager router llm for a youtube video script generator, note that it can be a facts video or a story kindof video. Note that the generation process is happening in different sections by the generator llm.

    This is the information,
    user's main request : {BaseState.user_prompt}
    context so far : {BaseState.progress_context}
    





    
    """



