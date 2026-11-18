# Clock module sources and compatibility limits

Sources checked on **2026-11-18**. This model family uses the complete **TFA
Dostmann 60.3065.02** analogue quartz insert, including its dial, hands, lens,
battery holder and time-setting control. It does not require a separate
controller or display circuit.

## Selected module: TFA Dostmann 60.3065.02

Primary sources:

- [Manufacturer product page](https://www.tfa-dostmann.de/en/product/analogue-quartz-clock-60-3065/)
- [Manufacturer instruction manual, page 1, Figures 1–3 and sections 5 and 9](https://com-tradebyte-core-tbone-media-live.s3.eu-central-1.amazonaws.com/media/1768/25729-618bd19257933.pdf)

| Property | Published value or operation | CAD implication |
| --- | --- | --- |
| Complete outer envelope | Diameter 90 mm, overall depth 36 mm | Reserve the complete insert envelope; the bezel overlaps the mounting opening. |
| Installation envelope | Diameter 77 mm, depth 22 mm | This is the manufacturer's installation size, not a manufacturing tolerance. |
| Device mass | 83 g, device only | Battery and the new housing add mass. |
| Power | One AA 1.5 V battery, supplied separately | No mains supply or additional electronics are required. |
| Service | Remove the rear lid to reach the battery and rotary time-setting wheel | Keep the rear accessible and allow the lid to be removed. |
| Attachment | A mounting ring is supplied | Final attachment must be checked with the actual ring and insert. |

The manual's page-1 drawing also contains a 74 mm diameter callout. Its PDF text
was extracted, but the drawing could not be visually inspected through the web
screenshot tool. The model therefore does not use that callout, nor assign
meaning to the extracted 15 mm and 8 mm callouts.

The design uses a **77.4 mm nominal sleeve bore and 22 mm installation depth**.
The additional 0.4 mm on diameter is a design allowance, not a TFA specification.
The sleeve is intended to accept the standard OEM mounting ring. Every housing
now has a removable rear cover; service requires opening that cover (and first
demounting the wall version). The rear-clearance assumption is geometric only.

The published sources do not establish ring geometry, retention force, any
thread size or pitch, allowable mounting-panel thickness, dimensional
tolerances, or the clearances needed to operate and remove the rear lid in this
new housing. Do not model an assumed OEM thread or claim that the ring is a
threaded retaining nut. The stated dimensions establish **nominal CAD
compatibility only**.

**Physical prototype gate:** measure the actual module and OEM ring, confirm
the sleeve fit and positive retention in every intended orientation, and check
battery replacement, time adjustment and rear-cap clearance. OEM ring retention
and real assembly fit remain **NOT_CHECKED** until this gate passes. This is a
prototype design, not a production-release fit guarantee.

## Alternatives considered

| Module | Source and relevant facts | Selection decision |
| --- | --- | --- |
| Velleman VM163 panel clock | [Manufacturer information sheet, page 1](https://cdn.velleman.eu/downloads/0/infosheets/vm163_uk.pdf): LED panel, 67 × 40.5 mm front, 54 × 37 mm cutout, 40 mm mounting depth; 9–15 V DC main supply; separate 4.5 V backup battery connection. | Reject for this battery-only insert family: backup power is separate from normal display power, and the module needs external supply wiring. |
| RVFM LCD-22 | [Rapid Electronics product record](https://www.rapidonline.com/lcd-clock-module-with-battery-70-0150): 20 mm diameter, 5 mm thick LCD clock with front setting buttons and SR41 battery. The listing marks it discontinued and states no replacement is listed. | Reject as the design reference: obsolete, with no current manufacturer mechanical drawing or dependable replacement established. |

Neither alternative's dimensions are interchangeable with the selected TFA
module. Availability, delivery to the user, acoustic behaviour and actual
timekeeping accuracy have not been verified by this source review.
