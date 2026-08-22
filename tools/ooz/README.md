# libooz.so — Oodle/Kraken decompressor for Palworld saves

Palworld v1.0 saves are `PlM1` containers whose payload is **Oodle Kraken**
compressed, not zlib — so `palworld-save-tools` cannot open them, and no
`oo2core` library ships with the game (it is statically linked).

Built from https://github.com/powzix/ooz with a Linux shim (`stdafx.linux.h`,
copied here as the `stdafx.h` used for the build):

    g++ -O2 -std=c++14 -fPIC -shared -w kraken_core.cpp bitknit.cpp lzna.cpp -o libooz.so

`kraken_core.cpp` is `kraken.cpp` truncated just before the
`OodLZ_CompressFunc` typedef, which drops the Windows-only CLI and DLL loader.
Shims needed: `_BitScanReverse/Forward`, `_byteswap_*`, `__popcnt`,
`__forceinline`. Do NOT shim `_rotl`/`_rotr` — GCC's `ia32intrin.h` already
defines them and they collide.

## Save layout

    0x00  uint32  uncompressed size
    0x04  uint32  compressed size
    0x08  char[4] "PlM1"
    0x0c  ...     Kraken stream (first byte 0x8c)

## Use

    import ctypes, struct
    lib = ctypes.CDLL("libooz.so")
    fn = lib._Z17Kraken_DecompressPKhmPhm      # C++ mangled
    fn.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                   ctypes.c_char_p, ctypes.c_size_t]
    fn.restype = ctypes.c_int
    d = open("Level.sav", "rb").read()
    unc, comp = struct.unpack_from("<II", d, 0)
    dst = ctypes.create_string_buffer(unc + 64)
    n = fn(d[12:12 + comp], comp, dst, unc)    # n == unc on success
    gvas = dst.raw[:n]                          # begins b"GVAS"
