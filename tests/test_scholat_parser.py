"""Scholat fetcher 纯函数解析测试 —— 不需要浏览器。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fetchers.scholat import (
    Homework,
    _infer_policy,
    _map_status,
    _to_event,
    parse_homework_detail,
    parse_homework_list,
)
from shared.models import SubmissionPolicy

_LIST_HTML = """
<table id="datalist">
  <tr>
    <td><a href="S_oneHomework.html?homeworkId=88&courseId=3017" title="第一次作业">第一次作业</a></td>
    <td id="upload88">未提交</td>
    <td>2026-11-01 23:59</td>
  </tr>
  <tr>
    <td><a href="S_oneHomework.html?homeworkId=89&courseId=3017" title="第二次作业">第二次作业</a></td>
    <td id="upload89">已提交</td>
    <td>2026-10-20 23:59</td>
  </tr>
</table>
"""

_DETAIL_HTML = """
<div class="notice_title">第一次作业（修订版）</div>
<div class="notice_d">发布人：张老师  截止时间：2026-11-01 23:59</div>
<div class="notice_content">请完成第三章习题 1-5。<br>注意格式规范。</div>
<a class="btn_down" href="S_downloadHomeworkLink.html?homeworkLinkId=42">
  <span title="template.docx">template.docx (12KB)</span>
</a>
"""


def test_parse_list_count():
    hws = parse_homework_list(_LIST_HTML, "3017")
    assert len(hws) == 2


def test_parse_list_fields():
    hws = parse_homework_list(_LIST_HTML, "3017")
    hw = hws[0]
    assert hw.homework_id == "88"
    assert hw.title == "第一次作业"
    assert hw.status == "未提交"
    assert hw.deadline == "2026-11-01 23:59"
    assert "S_oneHomework" in hw.url


def test_parse_list_submitted():
    hws = parse_homework_list(_LIST_HTML, "3017")
    assert hws[1].status == "已提交"
    assert hws[1].homework_id == "89"


def test_parse_detail_updates_title():
    hw = Homework("88", "第一次作业", "未提交", "https://www.scholat.com/course/S_oneHomework.html?homeworkId=88")
    hw = parse_homework_detail(_DETAIL_HTML, hw)
    assert hw.title == "第一次作业（修订版）"


def test_parse_detail_publisher_deadline():
    hw = Homework("88", "", "未提交", "")
    hw = parse_homework_detail(_DETAIL_HTML, hw)
    assert hw.publisher == "张老师"
    assert hw.deadline == "2026-11-01 23:59"


def test_parse_detail_content():
    hw = Homework("88", "", "未提交", "")
    hw = parse_homework_detail(_DETAIL_HTML, hw)
    assert "第三章" in hw.content
    assert "格式规范" in hw.content


def test_parse_detail_attachment():
    hw = Homework("88", "", "未提交", "")
    hw = parse_homework_detail(_DETAIL_HTML, hw)
    assert len(hw.attachments) == 1
    assert hw.attachments[0]["name"] == "template.docx"
    assert hw.attachments[0]["link_id"] == "42"


# 2026-10 学者网真实列表行结构（匿名化）：状态是徽章，截止日期格带提交规则徽章，操作栏有"已交"
_REAL_ROW_HTML = """
<table id="datalist">
<tr class="altrow">
<td id="upload39585">
<span style="padding:2px 7px;color: white;background:#39d239;border-radius:10px;font-size:12px;">按时提交</span>
</td>
<td style="text-align:center;">
<a href="S_oneHomework.html?courseId=3017&amp;homeworkId=39585" title="实验3-栈与队列">实验3-栈与队列</a>
</td>
<td><a href="../teacher" target="_blank">某老师</a></td>
<td>
<span style="font-size:13px;">2026-11-05</span><br/>
<span style="padding:1px 8px;color:white;background:#3acbdc;border-radius:8px;font-size:12px;">不可延时提交</span>
</td>
<td style="padding-left:8px;">
<a href="S_oneHomework.html?courseId=3017&amp;homeworkId=39585"><span>作业要求</span></a> |
<a onclick="showinfo('3017','39585','1','2')" style="cursor:pointer;">已交</a>
| <a href="#" onclick="showfilesend(39585, 1)">修改</a>
</td>
<td></td>
<td><span style="color:#aaa;">空</span></td>
</tr>
</table>
"""


def test_parse_real_row():
    hw = parse_homework_list(_REAL_ROW_HTML, "3017")[0]
    assert hw.homework_id == "39585"
    assert hw.title == "实验3-栈与队列"
    assert hw.status == "按时提交"
    assert hw.publisher == "某老师"
    assert hw.deadline == "2026-11-05"
    assert hw.policy_raw == "不可延时提交"
    assert hw.submitted_link is True


def test_real_row_to_event():
    ev = _to_event(parse_homework_list(_REAL_ROW_HTML, "3017")[0], "3017")
    assert ev.status == "submitted"
    assert ev.submission_policy == SubmissionPolicy.NONE
    assert ev.end_at == datetime(2026, 11, 5, 15, 59, 59, tzinfo=timezone.utc)  # 当天 23:59:59 CST
    assert ev.raw_payload["status_raw"] == "按时提交"


@pytest.mark.parametrize("raw,link,expected", [
    ("未提交", False, "open"),
    ("按时提交", False, "submitted"),
    ("延时提交", False, "submitted"),
    ("已终止提交", True, "submitted"),
    ("已终止提交", False, "closed"),
    ("奇怪的新状态", True, "submitted"),
    ("奇怪的新状态", False, "unknown"),
])
def test_map_status(raw, link, expected):
    assert _map_status(raw, link) == expected


@pytest.mark.parametrize("raw,expected", [
    ("不可延时提交", SubmissionPolicy.NONE),
    ("截止后可补交一次", SubmissionPolicy.ONCE),
    ("可延时提交", SubmissionPolicy.LATE),
    ("", SubmissionPolicy.NONE),
])
def test_infer_policy(raw, expected):
    assert _infer_policy(raw) == expected
