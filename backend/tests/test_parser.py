from pathlib import Path

from app.agents.parser.agent import PaperParserAgent


def test_parser_returns_structured_knowledge(tmp_path: Path):
    paper = tmp_path / "paper.pdf"
    paper.write_text("A Vision Paper\nAbstract\nWe propose an encoder decoder model.\nTraining uses Adam.", encoding="utf-8")

    bundle = PaperParserAgent().run(paper)

    assert bundle.paper.metadata.title == "A Vision Paper"
    assert bundle.paper.metadata.source_filename == "paper.pdf"
    assert isinstance(bundle.paper.architecture, list)

