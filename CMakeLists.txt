cmake_minimum_required(VERSION 3.5)
project(cmake_wrapper)

# hack ...
find_package(cpptoml REQUIRED)
include_directories(${cpptoml_INCLUDE_DIR})

if(LINUX)
  find_package(acl REQUIRED)
  include_directories(${acl_INCLUDE_DIR})
endif()

add_subdirectory("iceoryx_meta")