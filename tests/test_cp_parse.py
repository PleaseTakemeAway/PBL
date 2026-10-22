"""커팅플랜 정답 읽기 (cutplan_agent/eval/cp_parse.py, drawing_refs.py). 합성 DXF 로 확인한다."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import ezdxf

from cutplan_agent.eval.cp_parse import as_rows, parse_attrs, read_cp
from cutplan_agent.eval.drawing_refs import coverage, find_drawings, parse_ref


def rect(msp, x, y, w, h):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True)


class DrawingRefsTest(unittest.TestCase):
    def test_parse_ref(self):
        cases = {
            "S-2120-002 1-1": ("S-2120", 2),
            "652-E-704-004 4-3 SEALING STRIP": ("652-E-704", 4),
            "D=D-1203-2-2-1\\PN=BASE": ("D-1203", 2),
            "D=EA-1361-2-2,3\\PN=S": ("EA-1361", 2),
            "204-E-205": None,  # 설비 태그만 있다
            "D=D-1203-22222\\PN=CONE": None,  # 도면 번호가 깨졌다
            "A240-S31803 t8 x 1850 x 4800 1 sh't": None,
            "SHELL": None,
        }
        for label, want in cases.items():
            self.assertEqual(parse_ref(label), want, label)

    def test_find_and_coverage(self):
        names = [
            "VP-S-2120-DWG-002_R0 (DETAIL OF BODY).dwg",
            "VP-EVP-D-1203-OTH-002_0_DETAIL OF BODY & SUPPORT LUG.pdf",
        ]
        self.assertEqual(find_drawings("S-2120", 2, names), [names[0]])
        self.assertEqual(find_drawings("D-1203", 2, names), [names[1]])
        self.assertEqual(find_drawings("S-2120", 4, names), [])
        cov = coverage(["S-2120-002 1-1", "S-2120-004 1-2", "SHELL"], names)
        self.assertEqual((cov["parts"], cov["with_ref"], cov["missing"]), (3, 2, 1))
        self.assertEqual(cov["missing_refs"], [("S-2120-004", 1)])


class NestingLayoutTest(unittest.TestCase):
    """판재 배치도: 판 테두리 + 판 라벨, 판 안의 부품 라벨 두 줄."""

    def build(self, path):
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        # 판 1: 판을 거의 다 채운 SHELL 하나
        rect(msp, 0, 0, 4800, 1850)
        rect(msp, 0, 0, 4768, 1843)
        msp.add_text("A240 t8 x 1850 x 4800 1 sh't", height=100).set_placement(
            (0, -300)
        )
        msp.add_text("S-2120-002 1-1", height=150).set_placement((500, 900))
        msp.add_text("SHELL", height=150).set_placement((500, 700))
        # 판 2: 선을 공유하는 삼각형 둘 (LINE), 라벨이 옆에 있는 원, 라벨 없는 같은 크기 사각형
        ox = 6000
        rect(msp, ox, 0, 1150, 700)
        msp.add_text("A283-C t6 x 700 x 1150 1 sh't", height=100).set_placement(
            (ox, -300)
        )
        a, b, c, d = (ox + 10, 10), (ox + 310, 10), (ox + 160, 210), (ox + 460, 210)
        for p, q in ((a, b), (b, c), (c, a), (b, d), (d, c)):
            msp.add_line(p, q)
        msp.add_text("S-2120-002 2-3", height=10).set_placement((ox + 140, 60))
        msp.add_text("COVER", height=10).set_placement((ox + 140, 45))
        msp.add_text("S-2120-002 2-3", height=10).set_placement((ox + 290, 170))
        msp.add_text("COVER", height=10).set_placement((ox + 290, 155))
        msp.add_circle((ox + 800, 100), 34)
        msp.add_text("S-2120-003 2-3", height=10).set_placement((ox + 840, 100))
        msp.add_text("END PLATE", height=10).set_placement((ox + 840, 85))
        rect(msp, ox + 600, 400, 200, 100)
        rect(msp, ox + 850, 400, 200, 100)
        msp.add_text("S-2120-002 2-5", height=10).set_placement((ox + 620, 450))
        msp.add_text("CONN PL", height=10).set_placement((ox + 620, 435))
        doc.saveas(path)

    def test_sheets_parts_pieces(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "cp.dxf"
            self.build(p)
            cp = read_cp(str(p))
            rows = as_rows(cp)
        self.assertEqual(cp.layout, "nesting")
        self.assertEqual(
            [
                (s["material"], s["thickness"], s["sheet_w"], s["sheet_h"])
                for s in rows["sheets"]
            ],
            [("A240", 8.0, 1850.0, 4800.0), ("A283-C", 6.0, 700.0, 1150.0)],
        )
        parts = {(r["item"], r["name"]): r for r in rows["parts"]}
        shell = parts[("1-1", "SHELL")]
        self.assertEqual(
            (shell["outline"], shell["w"], shell["h"]), ("label", 4768.0, 1843.0)
        )
        covers = [r for r in rows["parts"] if r["name"] == "COVER"]
        self.assertEqual([r["outline"] for r in covers], ["face", "face"])
        self.assertEqual({r["area"] for r in covers}, {30000})
        end = parts[("2-3", "END PLATE")]
        self.assertEqual((end["outline"], end["dwg_ref"]), ("near", "S-2120-003"))
        conn = parts[("2-5", "CONN PL")]
        self.assertEqual((conn["outline"], conn["n_pieces"]), ("label", 2))
        links = sorted(r["link"] for r in rows["pieces"])
        self.assertIn("copy", links)
        self.assertNotIn("", links)  # 판 테두리와 남은 자리는 조각이 아니다


class UnfoldListTest(unittest.TestCase):
    """전개도 모음: 줄마다 큰 아이템 번호, 전개도 안에 D=..\\PN=.. 속성 글자."""

    def build(self, path):
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        msp.add_text("002-1-2", height=400).set_placement((0, 10000))
        msp.add_circle((3000, 10000), 1000)
        msp.add_lwpolyline([(4500, 9000), (5500, 9000), (5500, 11000)], close=True)
        msp.add_mtext(
            "D=D-1203-2\\PN=HEAD\\PM=SA240-304L\\PT=23\\PS=%%C2000\\PQ=1"
        ).set_location((2900, 10100))
        msp.add_text("003-1-3", height=400).set_placement((0, 6000))
        msp.add_circle((3000, 6000), 576.5)
        msp.add_circle((3000, 6000), 305)
        msp.add_mtext(
            "D=D-1203-2\\PN=M1/24\\PM=SA240-304L\\PT=25\\PS=%%C610x\\P%%C1153\\PQ=1"
        ).set_location((2950, 6050))
        doc.saveas(path)

    def test_items_and_rows(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "cp.dxf"
            self.build(p)
            cp = read_cp(str(p), tag="D-1203")
            rows = as_rows(cp)
        self.assertEqual(cp.layout, "unfold_list")
        head, ring = rows["parts"]
        self.assertEqual(
            (
                head["dwg_ref"],
                head["item"],
                head["name"],
                head["thickness"],
                head["size"],
            ),
            ("D-1203-002", "1-2", "HEAD", 23.0, "Ø2000"),
        )
        self.assertEqual(head["n_pieces"], 2)  # 라벨 없는 분할 조각은 같은 줄로 묶인다
        self.assertEqual(ring["dwg_ref"], "D-1203-003")  # 줄 번호가 D= 보다 우선
        self.assertEqual(
            (ring["w"], ring["holes"]), (1153.0, 1)
        )  # 구멍이 아니라 바깥 링
        self.assertEqual(ring["size"], "Ø610xØ1153")

    def test_parse_attrs(self):
        a = parse_attrs("D=D-1203-2-2-1\nN=BASE\nPL\nM=SA285-C\nT=70\nS=566\nx490\nQ=4")
        self.assertEqual(
            a,
            {
                "dwg": "D-1203-2-2-1",
                "name": "BASE PL",
                "material": "SA285-C",
                "thickness": "70",
                "size": "566x490",
                "qty": "4",
            },
        )


if __name__ == "__main__":
    unittest.main()
