COINES_INSTALL_PATH ?= C:/COINES_SDK_main

EXAMPLE_FILE ?= bme69x_bridge_cli.c
API_LOCATION ?= $(COINES_INSTALL_PATH)/examples/BME690_SensorAPI-master

C_SRCS += \
$(API_LOCATION)/bme69x.c \
$(API_LOCATION)/examples/common/common.c

INCLUDEPATHS += \
$(API_LOCATION) \
$(API_LOCATION)/examples/common

COINES_BACKEND ?= COINES_BRIDGE

include $(COINES_INSTALL_PATH)/coines.mk
