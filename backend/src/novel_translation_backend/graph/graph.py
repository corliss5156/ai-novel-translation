from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_REVISE,
)
from novel_translation_backend.graph.nodes.glossary_extractor import (
    glossary_extractor_node,
)
from novel_translation_backend.graph.nodes.complete import complete_node
from novel_translation_backend.graph.nodes.editor import editor_node
from novel_translation_backend.graph.nodes.glossary_db_write import (
    glossary_db_write_node,
)
from novel_translation_backend.graph.nodes.hitl_final import hitl_final_node
from novel_translation_backend.graph.nodes.hitl_glossary import hitl_glossary_node
from novel_translation_backend.graph.nodes.s3_retrieval import s3_retrieval_node
from novel_translation_backend.graph.nodes.translator import translator_node
from novel_translation_backend.graph.state import WorkflowState


def route_after_glossary_extraction(
    state: WorkflowState,
) -> Literal["hitl_glossary", "glossary_db_write"]:
    if any(term["is_new"] for term in state["glossary_terms"]):
        return "hitl_glossary"
    return "glossary_db_write"


def route_final_review(state: WorkflowState) -> Literal["editor", "complete"]:
    if state["status"] == WORKFLOW_STATUS_REVISE:
        return "editor"
    return "complete"


workflow = StateGraph(WorkflowState)

workflow.add_node("s3_retrieval", s3_retrieval_node)
workflow.add_node("glossary_extractor", glossary_extractor_node)
workflow.add_node("hitl_glossary", hitl_glossary_node)
workflow.add_node("glossary_db_write", glossary_db_write_node)
workflow.add_node("translator", translator_node)
workflow.add_node("editor", editor_node)
workflow.add_node("hitl_final", hitl_final_node)
workflow.add_node("complete", complete_node)

workflow.add_edge(START, "s3_retrieval")
workflow.add_edge("s3_retrieval", "glossary_extractor")
workflow.add_conditional_edges("glossary_extractor", route_after_glossary_extraction)
workflow.add_edge("hitl_glossary", "glossary_db_write")
workflow.add_edge("glossary_db_write", "translator")
workflow.add_edge("translator", "editor")
workflow.add_edge("editor", "hitl_final")
workflow.add_conditional_edges("hitl_final", route_final_review)
workflow.add_edge("complete", END)

checkpointer = InMemorySaver()
graph = workflow.compile(checkpointer=checkpointer)

# graph.get_graph().draw_mermaid_png(output_file_path="graph_output.png")
