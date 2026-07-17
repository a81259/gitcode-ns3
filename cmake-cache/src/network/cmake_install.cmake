# Install script for directory: /home/a81257/gitcode0519/ns-3-ub-next/src/network

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
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so"
         RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/a81257/gitcode0519/ns-3-ub-next/build/lib/libns3.44-network.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so"
         OLD_RPATH "/home/a81257/gitcode0519/ns-3-ub-next/build/lib::::::::::::::::::::::::::::::::::"
         NEW_RPATH "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.44-network.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/application-container.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/application-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/delay-jitter-estimation.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/net-device-container.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/node-container.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/packet-socket-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/simple-net-device-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/helper/trace-helper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/application.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/buffer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/byte-tag-list.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/channel-list.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/channel.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/chunk.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/header.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/net-device.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/nix-vector.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/node-list.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/node.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/packet-metadata.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/packet-tag-list.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/packet.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/socket-factory.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/socket.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/tag-buffer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/tag.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/model/trailer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/test/header-serialization-test.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/address-utils.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/bit-deserializer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/bit-serializer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/crc32.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/data-rate.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/drop-tail-queue.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/dynamic-queue-limits.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/error-channel.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/error-model.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/ethernet-header.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/ethernet-trailer.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/flow-id-tag.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/generic-phy.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/inet-socket-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/inet6-socket-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/ipv4-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/ipv6-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/llc-snap-header.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/lollipop-counter.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/mac16-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/mac48-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/mac64-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/mac8-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/net-device-queue-interface.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/output-stream-wrapper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-burst.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-data-calculators.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-probe.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-socket-address.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-socket-client.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-socket-factory.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-socket-server.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packet-socket.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/packetbb.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/pcap-file-wrapper.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/pcap-file.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/pcap-test.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/queue-fwd.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/queue-item.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/queue-limits.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/queue-size.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/queue.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/radiotap-header.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/sequence-number.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/simple-channel.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/simple-net-device.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/sll-header.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/src/network/utils/timestamp-tag.h"
    "/home/a81257/gitcode0519/ns-3-ub-next/build/include/ns3/network-module.h"
    )
endif()

