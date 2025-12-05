from __future__ import annotations

import json
from typing import Iterable, TYPE_CHECKING

from ...models import IdeaRecord, Task
from ...runtime.harmony_client import HarmonyRequest

if TYPE_CHECKING:
    from ..loop import AgentContext


class PromptBuilder:
    ROLE_MAP = {
        "plan": "planner",
        "ideate": "ideator",
        "critic": "critic",
        "edit": "editor",
        "shake_up_idea": "ideator",
        "research": "researcher",
    }

    def __init__(self, context: "AgentContext") -> None:
        self.context = context

    def role_for_task(self, task_type: str) -> str:
        return self.ROLE_MAP.get(task_type, "planner")

    def build(
        self,
        task: Task,
        *,
        related_ideas: Iterable[IdeaRecord] = (),
        recent_summaries: list[str] | None = None,
        search_results: list[dict[str, str]] | None = None,
    ) -> HarmonyRequest:
        role = self.role_for_task(task.type)
        system = self._system_prompt()
        developer = self._developer_prompt(role)
        user = self._task_instructions(
            task, role, related_ideas, recent_summaries, search_results or []
        )
        context = {"search_hits": search_results} if search_results else None
        return HarmonyRequest(system=system, developer=developer, user=user, context=context)

    def _system_prompt(self) -> str:
        ip = self.context.ip_profile
        return (
            f"あなたは{ip.ip_name}であり、{ip.essence}です。 "
            f"ブランドプロミス: {ip.brand_promise}。避けるべきこと: {', '.join(ip.taboos)}。"
        )

    def _developer_prompt(self, role: str) -> str:
        ip = self.context.ip_profile
        project = self.context.project_config
        constraints = ", ".join(f"{k}: {v}" for k, v in project.constraints.items())
        templates = " | ".join(project.idea_templates)
        developer_lines = [
            "# IP仕様",
            f"名前: {ip.ip_name}",
            f"本質: {ip.essence}",
            f"人格: {', '.join(ip.core_personality)}",
            f"ビジュアルモチーフ: {', '.join(ip.visual_motifs)}",
            f"タブー: {', '.join(ip.taboos)}",
            "# プロジェクト設定",
            f"プロジェクト: {project.project_name}",
            f"目標: {project.goal_type}",
            f"ターゲット: {ip.target_audience}",
            f"制約: {constraints}",
            f"アイデアテンプレート: {templates}",
            f"イテレーションポリシー: {json.dumps(project.iteration_policy)}",
            "# 役割",
            f"このイテレーションでは{role}として行動してください。",
            "出力は必ず JSON 形式のみで返し、ideas / follow_up_tasks / summary の3キーを必須で含めてください。",
            "平文の説明や別フォーマットは不要です。",
        ]
        return "\n".join(developer_lines)

    def _task_instructions(
        self,
        task: Task,
        role: str,
        related_ideas: Iterable[IdeaRecord],
        recent_summaries: list[str] | None,
        search_results: list[dict[str, str]],
    ) -> str:
        related = ", ".join(task.related_idea_ids) if task.related_idea_ids else "なし"
        base = [
            f"このイテレーションでは{role}として行動してください。",
            "出力は必ず JSON のみ。必須キー: ideas (リスト), follow_up_tasks (リスト), summary (文字列)。",
            "JSON 以外のテキストは一切返さないでください。",
        ]
        if related_ideas:
            base.append("## 関連アイデア")
            for idea in related_ideas:
                base.append(
                    " - "
                    + json.dumps(
                        {
                            "id": idea.id,
                            "title": idea.title,
                            "summary": idea.summary,
                            "tags": idea.tags,
                            "scores": {
                                "brand_fit": idea.brand_fit_score,
                                "novelty": idea.novelty_score,
                                "feasibility": idea.feasibility_score,
                            },
                        },
                        ensure_ascii=False,
                    )
                )
        if task.type == "shake_up_idea":
            base.append(
                "アイデアを揺さぶってください。JSONで返却し、キーは ideas（少なくとも2つの方向性）、"
                "follow_up_tasks、summary としてください。",
            )
            if recent_summaries:
                base.append("重複を避けるための最近のサマリー:")
                for entry in recent_summaries[-3:]:
                    base.append(f" - {entry}")
            base.append("新しい方向性が最近の更新と明確に異なるようにしてください。")
        elif role == "planner":
            base.append(
                "プロジェクトを前進させるフォローアップタスクを提案してください。"
                " JSONで返却し、キーは follow_up_tasks（リスト）、summary としてください。",
            )
        elif role == "ideator":
            base.append(
                "提供されたテンプレートに沿ってビジネスアイデアを生成してください。"
                " JSONで返却し、キーは ideas（アイデア記録のリスト）、"
                " follow_up_tasks、summary としてください。",
            )
        elif role == "critic":
            base.append(
                "既存のアイデアをレビューし、改善点を提案してください。"
                " JSONで返却し、キーは ideas（改訂案のリスト。任意）、"
                " follow_up_tasks（リスト）、summary としてください。",
            )
        elif role == "editor":
            base.append(
                "選択されたアイデアを磨き上げ、準備完了かを示してください。"
                " JSONで返却し、キーは ideas（リスト）、follow_up_tasks（任意のリスト）、"
                "summary としてください。",
            )
        elif role == "researcher":
            base.append(
                "指定されたクエリについて外部検索のヒットを読み、短く要約してください。"
                " JSONで返却し、キーは ideas（関連する洞察や機会のリスト。任意）、"
                " follow_up_tasks（追加リサーチやアクション項目のリスト）、summary としてください。",
            )
        if search_results:
            base.append("## 外部リサーチ結果")
            base.append(
                "以下の検索結果を参考にしてください。要約や引用を行う場合は番号を明示してください。"
            )
            for idx, hit in enumerate(search_results, start=1):
                base.append(
                    f"{idx}. {hit.get('title', '')} ({hit.get('href', '')}) - {hit.get('snippet', '')}"
                )
        if task.meta:
            base.append(f"タスクの補足: {json.dumps(task.meta)}")
        base.append(f"関連アイデア: {related}")
        return "\n".join(base)
