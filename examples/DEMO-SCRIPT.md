# 90-second demo script

Total target: 75-85 s. Screen-record Telegram (phone) or the Hermes desktop chat.

**0:00-0:08 Hook, say it over the empty chat**
"Agents are bad at surveying math. Bearings, closure, datum shifts. So I gave Hermes a survey desk."

**0:08-0:30 Good field book**
Paste `examples/demo-fieldbook.txt` after `/survey `. Hermes replies with the plan image.
Point at: area 1.5324 ha, relative accuracy 1:12,812, "all internal checks passed".
Say: "Closure, area by two independent methods, and a check that the boundary doesn't cross itself."

**0:30-0:45 The KML**
Tap the KML in chat, open in Google Earth. The parcel sits on the ground.
Say: "Georeferenced from Minna datum, and it tells you the datum shift is about 15 metres."

**0:45-1:10 The blunder**
Paste the same field book with `87.05` changed to `78.05` (a digit transposition).
Hermes replies RE-OBSERVE, relative accuracy 1:51, and: "Suspect leg D-E: 78.05 -> 87.087".
Say: "Same typo any field book has. It finds the leg and the value it should have been."

**1:10-1:20 Close**
"survey-desk. Exact survey math for Hermes. Tests, no network calls, in the catalog."
Tag @NousResearch.
