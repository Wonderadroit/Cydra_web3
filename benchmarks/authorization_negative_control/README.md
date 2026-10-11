# Protected authorization negative control

This benchmark uses the safe fixture preserved in Wonderadroit/Cydra_wonder at pinned source commit 99f43987376a327c423ddde2877ce9995564d254. It is a control, not a bounty target.

Expected result: CYDRA may generate a hypothesis, but the executed unauthorized-caller test must observe that the target's state gate prevents the modeled mutation. The classification must be not_confirmed. This does not prove all authorization behavior is secure; it validates one protected control.
