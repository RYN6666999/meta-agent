#!/usr/bin/env python3
"""Build a SurveyCake-ready survey package from the Gemini final questionnaire template."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR_DEFAULT = ROOT_DIR / 'memory' / 'surveycake-output'


def gemini_final_template() -> dict:
    return {
        'template_id': 'gemini-final-v1',
        'title': '【講座名稱】專屬課前問卷',
        'description': (
            '哈囉！歡迎報名本次的講座。\n\n'
            '為了確保這次內容能精準切中您的需求，並帶來最大的收穫，'
            '請協助花 1~2 分鐘填寫這份課前問卷。\n\n'
            '您的回覆僅供講師備課與現場交流參考，我們會妥善保管資料。'
        ),
        'sections': [
            {
                'title': '第一部分：基本認識',
                'questions': [
                    {
                        'id': 'q1_name',
                        'type': 'text',
                        'title': '姓名 / 暱稱',
                        'required': True,
                    },
                    {
                        'id': 'q2_age_range',
                        'type': 'single_choice',
                        'title': '您的年齡區間',
                        'required': True,
                        'choices': ['20-25歲', '26-30歲', '31-40歲', '41-50歲', '50歲以上'],
                    },
                    {
                        'id': 'q3_channel',
                        'type': 'text',
                        'title': '請問您是透過誰，或哪個管道得知本講座的呢？',
                        'required': True,
                    },
                    {
                        'id': 'q4_sign',
                        'type': 'text',
                        'title': '您的星座是？（選填）',
                        'required': False,
                    },
                ],
            },
            {
                'title': '第二部分：現況與背景',
                'questions': [
                    {
                        'id': 'q5_job',
                        'type': 'text',
                        'title': '您目前的職業與產業領域是？（例如：科技業/行銷企劃）',
                        'required': True,
                    },
                    {
                        'id': 'q6_exp',
                        'type': 'single_choice',
                        'title': '您目前的總工作年資大約是？',
                        'required': True,
                        'choices': ['1年以下', '1-3年', '4-7年', '8-10年', '10年以上'],
                    },
                    {
                        'id': 'q7_finance_profile',
                        'type': 'multi_choice',
                        'title': '關於財務與理財現況，您目前符合以下哪些描述呢？（可複選）',
                        'required': True,
                        'choices': [
                            '有固定薪資收入（薪轉）',
                            '有投資理財習慣（股票、基金、虛擬貨幣等）',
                            '已為自己規劃商業保險',
                            '名下有房地產（或家人有）',
                            '有使用信用卡消費的習慣',
                            '有貸款或負債正在償還中',
                        ],
                    },
                ],
            },
            {
                'title': '第三部分：價值觀與痛點',
                'questions': [
                    {
                        'id': 'q8_priority',
                        'type': 'multi_choice',
                        'title': '現階段的人生中，您覺得以下哪兩項對您來說最重要？（請勾選 2 項）',
                        'required': True,
                        'max_select': 2,
                        'choices': [
                            '家庭 (Family)',
                            '工作與事業 (Occupation)',
                            '休閒興趣 (Recreation)',
                            '財務狀況 (Money)',
                            '個人夢想 (Dream)',
                            '身體健康 (Health)',
                        ],
                    },
                    {
                        'id': 'q9_pain_dream',
                        'type': 'paragraph',
                        'title': '目前生活中，您遇到最大的痛點/煩惱，或最想達成的夢想是什麼？',
                        'required': True,
                    },
                    {
                        'id': 'q10_interest',
                        'type': 'paragraph',
                        'title': '這次報名本講座，主要是對什麼主題或能力最感興趣？',
                        'required': True,
                    },
                ],
            },
            {
                'title': '第四部分：期待與決策',
                'questions': [
                    {
                        'id': 'q11_decision_mode',
                        'type': 'single_choice',
                        'title': '若未來有進修、投資或重大花費的計畫，您通常是如何做決定的？',
                        'required': True,
                        'choices': ['我可以自己做主', '習慣先與家人或伴侶討論'],
                    },
                    {
                        'id': 'q12_fee_awareness',
                        'type': 'single_choice',
                        'title': '關於後續延伸學習的學費方案，您的了解程度是？',
                        'required': True,
                        'choices': [
                            '已有初步了解，想聽完講座後評估是否投入',
                            '尚不清楚，希望在講座中了解相關資訊',
                        ],
                    },
                    {
                        'id': 'q13_ask_teacher',
                        'type': 'paragraph',
                        'title': '最後，對於本次講座，您有什麼最想問講師的問題嗎？（選填）',
                        'required': False,
                    },
                ],
            },
        ],
        'confirmation_message': (
            '感謝您的填寫！我們已經收到您的回覆。\n'
            '請記得將講座時間加入行事曆，我們到時候見。\n'
            '若有任何問題，歡迎聯繫 [請填入聯絡窗口/LINE官方帳號]。'
        ),
    }


def render_markdown_manual(spec: dict) -> str:
    lines: list[str] = []
    lines.append(f"# {spec['title']}")
    lines.append('')
    lines.append('## 表單說明')
    lines.append(spec['description'])
    lines.append('')
    lines.append('## SurveyCake 建立步驟（手動 3-5 分鐘）')
    lines.append('1. 在 SurveyCake 新增一份空白問卷。')
    lines.append('2. 將問卷標題與表單說明貼上。')
    lines.append('3. 依下方各段落逐題新增。')
    lines.append('4. 需要限制最多勾選 2 項的題目，請在該題的選項限制設定 max=2。')
    lines.append('5. 將提交後訊息設定為本文末內容。')
    lines.append('')

    qn = 1
    for section in spec['sections']:
        lines.append(f"## {section['title']}")
        lines.append('')
        for q in section['questions']:
            required = '必填' if q.get('required') else '選填'
            qtype = q.get('type', 'text')
            lines.append(f"{qn}. {q['title']}")
            lines.append(f"   - 題型: {qtype}")
            lines.append(f"   - 設定: {required}")
            if 'max_select' in q:
                lines.append(f"   - 限制: 最多勾選 {q['max_select']} 項")
            if q.get('choices'):
                lines.append('   - 選項:')
                for c in q['choices']:
                    lines.append(f'     - {c}')
            lines.append('')
            qn += 1

    lines.append('## 提交後確認訊息')
    lines.append(spec['confirmation_message'])
    lines.append('')
    return '\n'.join(lines)


def build_score_guide() -> dict:
    return {
        'version': 'v1',
        'logic': [
            {
                'id': 'hot_intent',
                'description': '學費了解程度高 + 決策可自行做主',
                'rule': {
                    'all': [
                        {'question_id': 'q12_fee_awareness', 'equals': '已有初步了解，想聽完講座後評估是否投入'},
                        {'question_id': 'q11_decision_mode', 'equals': '我可以自己做主'},
                    ]
                },
                'tag': 'A',
            },
            {
                'id': 'warm_intent',
                'description': '有興趣但需進一步教育',
                'rule': {
                    'any': [
                        {'question_id': 'q12_fee_awareness', 'equals': '尚不清楚，希望在講座中了解相關資訊'},
                        {'question_id': 'q11_decision_mode', 'equals': '習慣先與家人或伴侶討論'},
                    ]
                },
                'tag': 'B',
            },
        ],
        'fallback_tag': 'C',
    }


def _js_string(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace("'", "\\'")
    escaped = escaped.replace('\n', '\\n')
    return f"'{escaped}'"


def render_google_apps_script(spec: dict) -> str:
    lines: list[str] = []
    lines.append('/**')
    lines.append(' * Auto-generated by scripts/build_survey_package.py')
    lines.append(' * Run createLectureForm() in Google Apps Script editor.')
    lines.append(' */')
    lines.append('function createLectureForm() {')
    lines.append(f"  var form = FormApp.create({_js_string(spec['title'])});")
    lines.append(f"  form.setDescription({_js_string(spec['description'])});")
    lines.append('  form.setProgressBar(true);')
    lines.append('')

    for section in spec['sections']:
        lines.append(f"  form.addPageBreakItem().setTitle({_js_string(section['title'])});")
        for q in section['questions']:
            q_type = q.get('type')
            q_title = _js_string(q['title'])
            required = 'true' if q.get('required') else 'false'
            if q_type == 'text':
                lines.append(f'  form.addTextItem().setTitle({q_title}).setRequired({required});')
            elif q_type == 'paragraph':
                lines.append(f'  form.addParagraphTextItem().setTitle({q_title}).setRequired({required});')
            elif q_type == 'single_choice':
                choices = q.get('choices', [])
                js_choices = ', '.join(_js_string(c) for c in choices)
                lines.append('  form.addMultipleChoiceItem()')
                lines.append(f'    .setTitle({q_title})')
                lines.append(f'    .setChoiceValues([{js_choices}])')
                lines.append(f'    .setRequired({required});')
            elif q_type == 'multi_choice':
                choices = q.get('choices', [])
                js_choices = ', '.join(_js_string(c) for c in choices)
                if 'max_select' in q:
                    max_select = int(q['max_select'])
                    lines.append('  var checkboxValidation = FormApp.createCheckboxValidation()')
                    lines.append(f'    .requireSelectAtMost({max_select})')
                    lines.append(f"    .setHelpText({_js_string(f'請最多勾選 {max_select} 項')})")
                    lines.append('    .build();')
                    lines.append('  form.addCheckboxItem()')
                    lines.append(f'    .setTitle({q_title})')
                    lines.append(f'    .setChoiceValues([{js_choices}])')
                    lines.append('    .setValidation(checkboxValidation)')
                    lines.append(f'    .setRequired({required});')
                else:
                    lines.append('  form.addCheckboxItem()')
                    lines.append(f'    .setTitle({q_title})')
                    lines.append(f'    .setChoiceValues([{js_choices}])')
                    lines.append(f'    .setRequired({required});')
            lines.append('')

    lines.append(f"  form.setConfirmationMessage({_js_string(spec['confirmation_message'])});")
    lines.append('  Logger.log(\'Published URL: \' + form.getPublishedUrl());')
    lines.append('  Logger.log(\'Edit URL: \' + form.getEditUrl());')
    lines.append('}')
    lines.append('')
    return '\n'.join(lines)


def write_outputs(spec: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')

    spec_file = output_dir / f'survey-spec-{ts}.json'
    manual_file = output_dir / f'surveycake-manual-{ts}.md'
    score_file = output_dir / f'survey-score-guide-{ts}.json'
    gas_file = output_dir / f'google-form-create-{ts}.gs'
    summary_file = output_dir / 'latest-survey-package.json'

    score = build_score_guide()
    manual = render_markdown_manual(spec)
    gas_script = render_google_apps_script(spec)

    spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    manual_file.write_text(manual, encoding='utf-8')
    score_file.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding='utf-8')
    gas_file.write_text(gas_script, encoding='utf-8')

    summary = {
        'ok': True,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'template': spec.get('template_id'),
        'files': {
            'spec': str(spec_file.relative_to(ROOT_DIR)),
            'manual': str(manual_file.relative_to(ROOT_DIR)),
            'score_guide': str(score_file.relative_to(ROOT_DIR)),
            'google_apps_script': str(gas_file.relative_to(ROOT_DIR)),
        },
    }
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build SurveyCake-ready package from Gemini final survey template.'
    )
    parser.add_argument(
        '--output-dir',
        default=str(OUT_DIR_DEFAULT),
        help='Directory for generated package files.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir).expanduser().resolve()
    spec = gemini_final_template()
    summary = write_outputs(spec=spec, output_dir=out_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
