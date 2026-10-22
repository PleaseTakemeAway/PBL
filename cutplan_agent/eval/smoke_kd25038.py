"""
API 없이 L3/L4 만 돌리는 smoke test — KDM 발표자료의 검증 사례 KD25038 (VP2V901C SLOPS TANK).

발표자료 수치:
  - 쉘 ID 2600, t10, A516-70. 코스 SA-01 1700 / SA-02 2400 (TL~TL 4100). 배치툴 조각: 8168 x 1700, 8168 x 2400
  - TOP HEAD 2:1 ELLIP ID 2600 → 블랭크 Ø3240, 판폭 2000 에 맞춰 1970 + 1270 (오프셋 350) 두 조각
  - BTM CONE → SB-04a/b 2604x2604, SB-05a/b 1219x1219
  - N-PAD 500x495 x4, LEG-PAD x2, LUG-PAD x2, BASE PLATE A283-C t25 x4
  - 실제 PO: t10 3장 (2438x9150 / 2000x10270 / 3048x8870) gross 5,486 kg, 활용률 58% → 77%

콘·패드·러그의 상세 치수는 발표자료에 없어 가정값이다 (주석 참조). 목적은 코드 경로 검증이지 수치 재현이 아니다.
"""

import json

from cutplan_agent.skills import knowledge as K
from cutplan_agent.skills import l2_relation as L2
from cutplan_agent.skills import l3_rules as L3
from cutplan_agent.skills import l4_verify as L4
from cutplan_agent.state import JobState, Trajectory, set_context


def main():
    st = JobState(job="KD25038_smoke", eval_mode=True)
    traj = Trajectory(st.job)
    set_context(st, traj)
    print("knowledge topics:", [t["topic"] for t in K.list_topics()])

    # ---- L2 (접근 B: 스펙 직접 입력) ----
    L2.set_part_spec(
        "SHELL",
        "cylinder",
        "A516-70",
        10,
        1,
        inner_dia=2600,
        courses=[1700, 2400],
        note="발표자료 KD25038",
    )
    L2.set_part_spec(
        "TOP HEAD",
        "head",
        "A516-70",
        10,
        1,
        inner_dia=2600,
        head_type="2:1 ellipsoidal",
        straight_flange=50,
    )
    L2.set_part_spec(
        "BTM CONE",
        "cone_frustum",
        "A516-70",
        10,
        1,
        large_inner_dia=2600,
        small_inner_dia=1250,
        cone_height=1170,
        note="가정: 상부 콘 2600→1250, h1170",
    )
    L2.set_part_spec(
        "BTM CONE 2",
        "cone_frustum",
        "A516-70",
        10,
        1,
        large_inner_dia=1250,
        small_inner_dia=202.7,
        cone_height=900,
        note="가정: 하부 콘 1250→202.7, h900",
    )
    L2.set_part_spec("N-PAD", "pad_ring", "A516-70", 10, 4, pad_od=500, pad_id=220)
    L2.set_part_spec(
        "LEG PAD",
        "flat",
        "A516-70",
        10,
        2,
        outline=[[0, 0], [480, 0], [480, 700], [0, 700]],
        note="가정 480x700",
    )
    L2.set_part_spec(
        "LUG PAD",
        "flat",
        "A516-70",
        10,
        2,
        outline=[[0, 0], [250, 0], [250, 300], [0, 300]],
        note="가정 250x300",
    )
    L2.set_part_spec(
        "BASE PLATE",
        "flat",
        "A283-C",
        25,
        4,
        outline=[[0, 0], [420, 0], [420, 420], [0, 420]],
    )

    # ---- L3 전개 + 분할 ----
    for i, p in enumerate(st.parts):
        v = L4.verify_part_spec(i)
        f = L3.unfold_part(i)
        s = L3.split_to_pieces(
            i, max_w=2438 if p.part_type != "head" else 2000
        )  # 헤드는 폭 2000 판 가정 (KDM 과 동일 조건)
        print(f"\n[{p.part_name:10s}] spec ok={v['ok']} {v['issues']}")
        print(
            "   unfold:",
            {
                k: f[k]
                for k in f
                if k in ("type", "blank_w", "blank_h", "blank_dia", "formula", "error")
            },
        )
        print(
            "   pieces:",
            [(x["label"], x["w"], x["h"], x["qty"]) for x in s.get("pieces", [])],
        )

    # ---- L3 네스팅 + L4 검증 + 출력 ----
    r = L3.nest_all(cut="gas", allow_custom=True)
    print(
        "\n== nest_all ==",
        json.dumps(
            {
                k: r[k]
                for k in ("groups", "n_sheets", "total_gross_kg", "overall_utilization")
            },
            ensure_ascii=False,
        ),
    )
    for g in r["detail"]:
        for sh in g.get("sheets", []):
            print(
                f"   {g['material']} t{g['thickness']:g}  sheet {sh['sheet_id']}: {sh['size']}  pieces={sh['n_pieces']} util={sh['utilization']:.0%} {sh['gross_kg']} kg  {sh['pieces']}"
            )
    print("== verify_nesting ==", L4.verify_nesting())
    por = L3.build_por()
    print("== POR ==")
    for row in por["rows"]:
        print(
            f"   {row['no']}. {row['part_name']} {row['spec']}  {row['material']}  {row['qty']} {row['unit']}  {row['weight_kg']} kg {row['remark']}"
        )
    print("   total", por["total_kg"], "kg   (KDM 실제 PO: t10 3장 5,486 kg + t25 판)")
    print("== CP DXF ==", L3.write_cutting_plan_dxf())
    print("== confidence ==", L4.confidence_report()["suggest"])
    print(
        "== HITL auto ==",
        L4.ask_human("H4", "POR 를 발주해도 되는가?", ["예", "아니오"], "예"),
    )
    st.save()
    traj.save()
    print("\nstate:", st.run_dir() / "state.json", " steps:", len(traj.steps))


if __name__ == "__main__":
    main()
