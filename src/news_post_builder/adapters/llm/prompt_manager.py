"""Prompt loading and formatting manager."""

from pathlib import Path

from news_post_builder.core.models import ExtractedArticle


class PromptManager:
    """Loads and formats versioned prompt templates."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        if prompts_dir is None:
            self.prompts_dir = (
                Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts"
            )
        else:
            self.prompts_dir = prompts_dir

    def get_prompt_path(self, version: str) -> Path:
        return self.prompts_dir / f"generate_{version}.md"

    def format_prompt(
        self,
        article: ExtractedArticle,
        version: str = "v1",
        headline_count: int = 3,
        description_count: int = 3,
        max_description_chars: int = 300,
        previous_headlines: list[str] | None = None,
        previous_descriptions: list[str] | None = None,
    ) -> str:
        prompt_file = self.get_prompt_path(version)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

        template = prompt_file.read_text(encoding="utf-8")

        # Format untrusted article context
        article_context_parts = [
            "<ARTICLE_METADATA>",
            f"Title: {article.title or 'N/A'}",
            f"Publisher/Site: {article.site_name or 'N/A'}",
            f"Publication Date: {article.publish_date or 'N/A'}",
            f"Source URL: {article.source_url or 'Pasted by user'}",
            "</ARTICLE_METADATA>",
            "",
            "<ARTICLE_BODY>",
            article.text,
            "</ARTICLE_BODY>",
        ]
        article_context = "\n".join(article_context_parts)

        # Format previous options for de-duplication in "more options" rounds
        previous_instruction = ""
        has_prev_h = bool(previous_headlines)
        has_prev_d = bool(previous_descriptions)

        if has_prev_h or has_prev_d:
            prev_parts = [
                "<PREVIOUSLY_GENERATED_OPTIONS>",
                "IMPORTANT: Do NOT repeat, duplicate, or closely paraphrase options below.",
            ]
            if has_prev_h and previous_headlines:
                prev_parts.append("Previously generated headlines:")
                for h in previous_headlines:
                    prev_parts.append(f"- {h}")
            if has_prev_d and previous_descriptions:
                prev_parts.append("Previously generated descriptions:")
                for d in previous_descriptions:
                    prev_parts.append(f"- {d}")
            prev_parts.append("</PREVIOUSLY_GENERATED_OPTIONS>")
            previous_instruction = "\n".join(prev_parts)

        return template.format(
            headline_count=headline_count,
            description_count=description_count,
            max_description_chars=max_description_chars,
            article_context=article_context,
            previous_options_instruction=previous_instruction,
        )
