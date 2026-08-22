#pragma once
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <stdint.h>
#if defined(__x86_64__) || defined(__i386__)
#include <x86intrin.h>
#endif

typedef unsigned char byte;
typedef unsigned char uint8;
typedef unsigned int uint32;
typedef uint64_t uint64;
typedef int64_t int64;
typedef signed int int32;
typedef unsigned short uint16;
typedef signed short int16;
typedef unsigned int uint;

// MSVC intrinsics used by ooz, expressed with GCC builtins.
template <class T>
static inline unsigned char _BitScanReverse(T *index, unsigned int mask) {
  if (!mask) return 0;
  *index = (T)(31 - __builtin_clz(mask));
  return 1;
}
template <class T>
static inline unsigned char _BitScanForward(T *index, unsigned int mask) {
  if (!mask) return 0;
  *index = (T)__builtin_ctz(mask);
  return 1;
}
template <class T>
static inline unsigned char _BitScanReverse64(T *index, unsigned long long mask) {
  if (!mask) return 0;
  *index = (T)(63 - __builtin_clzll(mask));
  return 1;
}

// GCC's ia32intrin.h supplies _rotl/_rotr but not these.
static inline unsigned short _byteswap_ushort(unsigned short v) { return __builtin_bswap16(v); }
static inline unsigned int _byteswap_ulong(unsigned int v) { return __builtin_bswap32(v); }
static inline unsigned long long _byteswap_uint64(unsigned long long v) { return __builtin_bswap64(v); }
static inline unsigned int __popcnt(unsigned int v) { return __builtin_popcount(v); }
#define __forceinline inline __attribute__((always_inline))
