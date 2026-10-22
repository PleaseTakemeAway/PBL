# -*- coding: utf-8 -*-
"""
Claude 클라이언트 생성 한 곳.

조직(organization) 수준에서 만든 API 키는 워크스페이스에 묶여 있지 않아서, 요청마다
`anthropic-workspace-id` 헤더로 어느 워크스페이스를 쓸지 알려줘야 한다 (없으면 400:
"This API key is not scoped to a workspace ..."). 두 가지 해결책:
  1) 콘솔에서 워크스페이스 안에 들어가 키를 만든다 (헤더 불필요)
  2) 환경변수 ANTHROPIC_WORKSPACE_ID=wrkspc_... 를 두면 여기서 헤더를 붙인다
"""

import os


def make_client():
    import anthropic

    headers = {}
    ws = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if ws:
        headers["anthropic-workspace-id"] = ws
    return anthropic.Anthropic(default_headers=headers or None)
