"""Scholat fetcher 纯函数解析测试 —— 不需要浏览器。"""

from __future__ import annotations

from fetchers.scholat import Homework, parse_homework_detail, parse_homework_list

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
