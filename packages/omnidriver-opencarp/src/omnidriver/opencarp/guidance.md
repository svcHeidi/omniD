# openCARP through omniD

Study keys are `<file>.par:<parameter>`, e.g. `nversion.par:gregion[0].g_il`.
`describe` lists every parameter with its type, default and bounds.

- Flags: write `true`/`false` in a study; omniD writes `1`/`0`. openCARP reads
  `no`, `off`, `yes`, `2` all as ON (F1).
- Counts size arrays: `stim[1].*` needs `num_stim >= 2`, or openCARP exits (F2).
  `num_stim` defaults to 2, so a case that omits it gets two stimuli (F7).
- Units: `dt` is in microseconds, `tend` in milliseconds (G2). `spacedt` must
  be <= `tend` (G1). The mesh axis `dx` is in micrometres (F3).
- A key assigned twice in a .par takes its last value (F8); omniD refuses to
  patch such a key.
- Strings: omniD always writes a `.par` string quoted (F13). An unquoted
  value containing `=` is silently truncated at the `=` (F10), so omniD
  refuses to write or read one unquoted; `""` is the empty string, not an
  absent value (F11); a string cannot contain `#`, because openCARP starts a
  comment there even inside quotes (F12).
- Relative paths resolve against the case directory, which is every step's
  working directory (F5).
- Defaults that make a run slow: mesher resolution 100 µm, tend 100 ms, dt 5 µs
  (G7). Pin `dx`, `nversion.par:tend` and `nversion.par:dt` for quick studies.
- Outputs: `out/vm.igb` holds every time step; `out/init_acts_vm_act-thresh.dat`
  holds one activation time per mesh point in point order, -1 if never
  activated (F6).
