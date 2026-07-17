#ifdef NS3_MODULE_COMPILATION 
    error "Do not include ns3 module aggregator headers from other modules these are meant only for end user scripts." 
#endif 
#ifndef NS3_MODULE_UNIFIED_BUS
    // Module headers: 
    #include <ns3/ub-traffic-gen.h>
    #include <ns3/ub-app.h>
    #include <ns3/ub-controller.h>
    #include <ns3/ub-datalink.h>
    #include <ns3/ub-datatype.h>
    #include <ns3/ub-header.h>
    #include <ns3/ub-ctp.h>
    #include <ns3/ub-link.h>
    #include <ns3/ub-modulo-sequence.h>
    #include <ns3/ub-port.h>
    #include <ns3/ub-small-fifo-queue.h>
    #include <ns3/ub-sliding-bitmap-window.h>
    #include <ns3/ub-switch.h>
    #include <ns3/ub-transaction.h>
    #include <ns3/ub-function.h>
    #include <ns3/ub-transport.h>
    #include <ns3/ub-retrans.h>
    #include <ns3/ub-routing-process.h>
    #include <ns3/ub-switch-allocator.h>
    #include <ns3/ub-utils.h>
    #include <ns3/ub-network-address.h>
    #include <ns3/ub-tp-connection-manager.h>
    #include <ns3/ub-ldst-api.h>
    #include <ns3/ub-ldst-thread.h>
    #include <ns3/ub-ldst-instance.h>
    #include <ns3/ub-congestion-control.h>
    #include <ns3/ub-caqm.h>
    #include <ns3/ub-dcqcn.h>
    #include <ns3/ub-flow-control.h>
    #include <ns3/ub-queue-manager.h>
    #include <ns3/ub-tag.h>
    #include <ns3/ub-fault.h>
#endif 