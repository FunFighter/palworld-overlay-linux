# Investigation notes

Things that cost real time to establish, recorded so nobody has to repeat them.

## Overwolf and the TH.GL Companion App on Linux

Overwolf has no Linux build; its own docs call macOS and Steam Deck
unsupported and Wine "experimental, often fails, not recommended".

The newer **TH.GL Companion App** is a standalone Windows app rather than an
Overwolf plugin, which sounds promising. Under Wine 11.9 it gets surprisingly
far — the installer is Inno Setup and runs, and `THGLBridgeHost.exe` (.NET 10
NativeAOT) actually starts, downloads its manifest and opens its named pipe.
It then fails for two structural reasons:

1. **Its memory reads go through a kernel driver.** `driver/THGLDriver.inf`
   declares `ServiceType = 1` (`SERVICE_KERNEL_DRIVER`) and the bridge calls
   `DeviceIoControl` against `THGLDriver.sys`, with `ntoskrnl.exe` imports.
   Wine has no NT kernel. Even where Wine's service manager reports
   "Driver started successfully", a Wine driver could only see processes in its
   own prefix — not Steam's Proton prefix where the game runs.
2. `THGLApp.exe` needs **WebView2**, which has no winetricks verb and does not
   install cleanly.

Lifting their offsets instead does not work either: `manifest.bin` is encrypted
(7.93 bits/byte entropy, magic `GTLAWLTS`).

Also worth knowing: they fork [Dumper-7](https://github.com/Encryqed/Dumper-7),
an Unreal Engine SDK generator, which is how the offsets are found.

## Why a normal always-on-top window cannot work

Under KWin, fullscreen windows occupy a **higher layer** than "keep above". A
browser or GTK window with keep-above set will be covered by a focused
fullscreen game no matter what window rule you write. The fix is a
`zwlr_layer_shell_v1` surface on the `OVERLAY` layer, which is why the host is
GTK3 + WebKit2 + gtk-layer-shell rather than anything simpler.

Related dead end: **Chrome ignores `--class`** and self-assigns
`chrome-<host>__-Default` (e.g. `chrome-127.0.0.1__-Default`), so KWin window
rules cannot even be targeted at a Chrome app window by the class you asked for.

## Two environment variables that are not optional

- `GDK_BACKEND=wayland` must be exported **before PyGObject imports Gtk**.
  PyGObject initialises GTK on import, so setting it inside `main()` is too
  late and layer-shell silently degrades to a normal X11 window.
- `WEBKIT_DISABLE_COMPOSITING_MODE=1`, or KWin kills the surface with
  `wp_linux_drm_syncobj_surface_v1` error 4, *"explicit sync is used, but no
  acquire point is set"*, immediately after the page finishes loading.
  `GDK_GL=disable` and `WEBKIT_DISABLE_DMABUF_RENDERER=1` also work; CPU
  compositing was chosen because it keeps the GPU free for the game.

## Coordinates

`https://cdn.th.gl/palworld/version.json` carries, per map, a Leaflet
`transformation` `[a, b, c, d]` and `bounds`, both **in raw game coordinates**:

    x_px = a * lng + b
    y_px = c * lat + d      with lat = location_x, lng = location_y

Check against Palpagos: `lng = -724399` gives
`0.000353395913859746 × -724399 + 256 = 0.0`, and `lng = 724399` gives `512` —
one 512 px tile at zoom 0. The same holds for `lat` against `c`/`d`.

Node blobs are CBOR encoded with `cbor-x` using `{useRecords: true, pack: true}`,
so a plain CBOR decoder will not read them. Each spawn is
`{p: [x, y, z], id}`, and for `dungeon_random` the `id` is the UE actor UAID,
e.g. `BP_DungeonPortalMarker_C_UAID_04421A9A5A3F461E01_1272672161`.

Do not use the widely-copied 2024 origins (`122500` / `-158100` / `458.355`) —
they predate v1.0 and place the player off-map.

## What the dedicated server does and does not expose

`/v1/api/players` gives `name`, `playerId`, `userId`, `ip`, `ping`,
`location_x`, `location_y`, `level`. Position refreshes roughly every 1.1 s
while moving; it simply stops changing when you stand still. There is **no z,
and no facing direction**.

There is **no world-actor endpoint**. Probing distinguishes cleanly, because
routes that exist answer 401 unauthenticated while absent routes answer 404:

| path | result |
|---|---|
| `info`, `metrics`, `settings`, `players` | 401 → exists |
| `actors`, `worldactors`, `world`, `objects`, `dungeons`, `spawns`, `entities`, `map`, `guilds`, `bases` | 404 → absent |

`/v1/api/metrics` is aggregate only: player count, server fps, in-game day,
base camp count, uptime.

## Active dungeons, and why they cannot be mapped

Palworld v1.0 saves are `PlM1` containers whose payload is **Oodle Kraken**,
not zlib, so `palworld-save-tools` cannot open them, and no `oo2core` library
ships with the game (statically linked). Build the open-source
[`ooz`](https://github.com/powzix/ooz) decompressor instead — see
[`tools/ooz/README.md`](../tools/ooz/README.md) for the Linux shim, the exact
compile line, and the header layout.

Decompressed, `Level.sav` *does* carry live dungeon state:

- **145 dungeon instances** — 127 `EPalDungeonType::Normal`, 18 `Fixed`
- 170 `PalDungeonPointMarkerSaveData` entries
- per instance: `InstanceId`, `MarkerPointId`, `DungeonSpawnAreaId`,
  `DungeonLevelName`, `BossState`, `DisappearTimeAt`, `MapObjectSaveData`
- per marker: `MarkerPointId`, `NextRespawnGameTime`, `ConnectedDungeonInstanceId`

But it cannot be put on a map:

- markers are bare GUIDs with no transform
- `DungeonSpawnAreaId` is a **biome bucket**, not a per-entrance identity —
  `Grass001` 15, `Forest002` 14, `Forest001` 11, `Volcano001` 10, `Snow001` 10,
  `Dessert001` 10, `Grass002` 8, `Yakushima001` 1, `Skyland001` 1
- the save never contains `DungeonPortalMarker` or any `UAID` string, so there
  is no join to TH.GL's pin ids
- brute-forcing every float32 and float64 `(x, y)` pair in all 37 MB against the
  175 known entrances matched only 6–8 of them — chance

Entrance positions live in the game's `.pak` level data, not the save. The only
practical source for *which* entrances are currently spawned is the game
client's memory.

Consolation: with 145 of ~155 open at any time, showing all entrances is within
about 6% of the live truth.

## Memory reading, if anyone wants to try

A Proton-run game is an ordinary Linux process, so `/proc/<pid>/mem` is
readable with `CAP_SYS_PTRACE` or root — no kernel driver needed, which makes
this *easier* on Linux than on Windows. Palworld ships **no kernel anti-cheat**
(no EAC, BattlEye or VAC), and single-player saves locally.

`scanmem` / `GameConqueror` plus the in-game coordinate readout on the map
screen (`M`) makes the initial search tractable. Player coordinates are a
contiguous float triple (a UE `FVector`), so searching for an `(x, y)` pair at
a 4-byte stride is a strong filter. Expect to redo it after each game patch.
