# Install script for directory: /home/a81257/gitcode0519/ns-3-ub-next/src/core

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/a81257/gitcode0519/ns-3-ub-next/build/lib/libns3.44-core.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so"
         OLD_RPATH "/home/a81257/gitcode0519/ns-3-ub-next/build/lib::::::::::::::::::::::::::::::::::"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-core.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/home/a81257/gitcode0519/ns-3-ub-next/build/include/ns3/core-config.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/int64x64-128.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/helper/csv-reader.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/helper/event-garbage-collector.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/helper/random-variable-stream-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/abort.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/ascii-file.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/ascii-test.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/assert.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/atomic-counter.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/attribute-accessor-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/attribute-construction-list.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/attribute-container.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/attribute-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/attribute.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/boolean.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/breakpoint.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/build-profile.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/calendar-scheduler.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/callback.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/command-line.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/config.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/default-deleter.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/default-simulator-impl.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/demangle.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/deprecated.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/des-metrics.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/double.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/enum.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/event-id.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/event-impl.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/fatal-error.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/fatal-impl.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/fd-reader.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/environment-variable.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/global-value.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/hash-fnv.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/hash-function.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/hash-murmur3.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/hash.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/heap-scheduler.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/int64x64-double.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/int64x64.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/integer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/length.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/list-scheduler.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/log-macros-disabled.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/log-macros-enabled.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/log.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/make-event.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/map-scheduler.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/math.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/names.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/node-printer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/nstime.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/object-base.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/object-factory.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/object-map.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/object-ptr-container.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/object-vector.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/object.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/pair.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/pointer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/priority-queue-scheduler.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/ptr.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/random-variable-stream.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/rng-seed-manager.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/rng-stream.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/scheduler.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/show-progress.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/shuffle.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/simple-ref-count.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/simulation-singleton.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/simulator-impl.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/simulator.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/singleton.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/string.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/synchronizer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/system-path.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/system-wall-clock-ms.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/system-wall-clock-timestamp.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/test.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/time-printer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/timer-impl.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/timer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/trace-source-accessor.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/traced-callback.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/traced-value.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/trickle-timer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/tuple.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/type-id.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/type-name.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/type-traits.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/uinteger.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/uniform-random-bit-generator.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/valgrind.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/vector.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/warnings.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/watchdog.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/realtime-simulator-impl.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/wall-clock-synchronizer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/val-array.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/core/model/matrix-array.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/build/include/ns3/core-module.h"
    )
endif()

