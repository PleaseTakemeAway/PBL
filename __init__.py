# -*- coding: utf-8 -*-
"""
cutplan_agent — 도면 → 자재목록 → 전개·분할 → 네스팅 → POR 를 수행하는 VLM 에이전트.

Skill 은 KDM 발표자료(KDMTECH_발표자료_통합.pptx, 2026-08-03)의 4계층을 그대로 따른다.

    L1 인식(Perception)      "무엇이 어디에 적혀 있나"      skills/l1_perception.py
    L2 관계·의미(Relation)   "무엇을 의미하고 무엇과 이어지나" skills/l2_relation.py   <- VLM 추론의 본체
    L3 계산·로직(Rules)      "수치를 계산"  (결정적, 검증됨)  skills/l3_rules.py
    L4 검증·HITL(Verify)     "저신뢰 항목은 사람이 확정"       skills/l4_verify.py

    knowledge/*.md           도메인 지식 prompt (L2 가 load_domain_prompt 로 불러옴)
    agent/orchestrator.py    Claude tool_runner 기반 오케스트레이터 + trajectory 로그
    eval/                    정답(dataset/gt) 대비 평가, API 없이 도는 smoke test
"""
__version__ = "0.1.0"
