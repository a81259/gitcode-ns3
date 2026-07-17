# Install script for directory: /home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus

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
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/a81257/gitcode0519/ns-3-ub-next/build/lib/libns3.44-unified-bus.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so"
         OLD_RPATH "/home/a81257/gitcode0519/ns-3-ub-next/build/lib::::::::::::::::::::::::::::::::::"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-unified-bus.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-traffic-gen.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-app.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-controller.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-datalink.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-datatype.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-header.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-ctp.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-link.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-modulo-sequence.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-port.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-small-fifo-queue.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-sliding-bitmap-window.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-switch.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-transaction.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-function.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-transport.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-retrans.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-routing-process.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-switch-allocator.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-utils.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-network-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-tp-connection-manager.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-ldst-api.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-ldst-thread.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-ldst-instance.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-congestion-control.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-caqm.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-dcqcn.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/protocol/ub-flow-control.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-queue-manager.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-tag.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/unified-bus/model/ub-fault.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/build/include/ns3/unified-bus-module.h"
    )
endif()

