cmake_minimum_required(VERSION 3.20)
project(brailab_wrapper LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- MinHook static lib (all under src/) ---
add_library(minhook STATIC
  src/minhook/src/buffer.c
  src/minhook/src/hook.c
  src/minhook/src/trampoline.c
)

if(CMAKE_SIZEOF_VOID_P EQUAL 4)
  target_sources(minhook PRIVATE src/minhook/src/hde/hde32.c)
else()
  target_sources(minhook PRIVATE src/minhook/src/hde/hde64.c)
endif()

target_include_directories(minhook PUBLIC
  src/minhook/include
  src/minhook/src
)

# --- Wrapper DLL ---
add_library(brailab_wrapper SHARED
  src/brailab_wrapper.cpp
)

target_include_directories(brailab_wrapper PRIVATE
  include
  src/minhook/include
)

target_link_libraries(brailab_wrapper PRIVATE
  minhook
  winmm
  user32
)

target_compile_definitions(brailab_wrapper PRIVATE BRAILAB_WRAPPER_EXPORTS)
set_target_properties(brailab_wrapper PROPERTIES OUTPUT_NAME "brailab_wrapper")
