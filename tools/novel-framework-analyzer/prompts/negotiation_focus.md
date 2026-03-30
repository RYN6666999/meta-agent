# 寧凡談判模式：專屬分析提示詞

「寧凡的談判場景」是本系統的核心分析主題，視為一級任務。

---

## 高價值場景識別

**核心條件：focal_character 必須是談判的主動參與者，不能只是旁觀或被動接受。**

下列情況不算談判場景：
- focal_character 坐在旁邊看別人談判
- focal_character 只是被問了一個問題
- focal_character 被別人試探，自己沒有反制

以下場景（focal_character 親自參與）才標記 `is_negotiation_scene = true`：

- 談判 / 討價還價 / 條件交換
- 借勢壓人 / 以退為進
- 試探底線 / 反向設局
- 用資訊差建立優勢
- 在弱勢位置取得主導權
- 表面妥協，實質推進目標
- 不直接衝突，透過結構與節奏控制對手
- 逼對方先表態
- 讓對方以為有選擇，但選項已被收窄

---

## 必須分析的談判維度

1. **他先看懂局了嗎？**
   在開口前，他是否已判斷清楚：誰有籌碼、誰有退路、誰在壓迫誰？

2. **他知道對方真正要什麼嗎？**
   他是否準確讀到對方的真欲望（而不只是表面要求）？

3. **他用了資訊保留嗎？**
   他是否故意不說某些事，讓對方先暴露底牌？

4. **他如何把弱勢轉成籌碼？**
   他是否把原本對自己不利的處境，轉成可交換或可利用的條件？

5. **他怎麼收窄對方的選擇？**
   他是否讓對方以為還有選擇，但實際上所有出路都通向他想要的結果？

6. **他的欲望顯示得比實際更小嗎？**
   他是否刻意低估自己的需求，以降低對方的戒心？

7. **他的節奏控制是什麼？**
   說話的停頓、讓步的時機、給出條件的順序，是否都是刻意設計？

8. **他把心變藏在哪裡？**
   他的真實態度轉折是否不直接說出，而是埋在行動或沉默中？

---

## negotiation_pattern_tags 可選值

```
low_posture_control        — 以低姿態取得掌控
borrowed_pressure          — 借第三方壓力
let_opponent_speak_first   — 讓對方先說，觀察底牌
exchange_probe             — 以小交換試探對方邊界
condition_redefinition     — 重新定義問題/條件
risk_transfer              — 把風險轉移給對方
fake_concession            — 假讓步（實際上沒有損失）
weakness_to_initiative     — 以弱勢反取主動
information_for_space      — 用資訊換取迴旋空間
rule_rewrite               — 不直接衝突，但改寫遊戲規則
bluff_detection            — 識破對方的虛張聲勢
tempo_control              — 透過節奏掌控而非語言取勝
```

---

## 分析結論規範

禁止：只說「寧凡很聰明」「很會談判」「心理素質強」。

必須說：
- 他在這場談判中看到了什麼（局）
- 他的初始心態是否讓他先佔優勢（心）
- 他真正想要什麼，是否隱藏了（欲）
- 他如何讓對手在心理上先退，再在條件上退（變）

---

## 談判場景輸出範例

```json
{
  "is_negotiation_scene": true,
  "negotiation_pattern_tags": [
    "weakness_to_initiative",
    "let_opponent_speak_first",
    "information_for_space"
  ],
  "negotiation_summary": {
    "initiative_holder": "寧凡（表面被動，實際主導）",
    "what_ning_fan_withheld": "他知道輝子需要解釋才能讓林川信任他",
    "how_posture_shifted": "從被試煉的學員 → 掌握輝子心理破綻的人",
    "key_turning_point": "寧凡問：為什麼你不殺我？這讓輝子被迫解釋自己的底線"
  }
}
```
