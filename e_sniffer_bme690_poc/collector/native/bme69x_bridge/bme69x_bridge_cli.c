/**
 * Minimal command-line bridge around the Bosch BME69x SensorAPI.
 * Accepts heater steps over stdin and prints measurements to stdout.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bme69x.h"
#include "coines.h"
#include "common.h"

#define CMD_BUFFER_SIZE         128
#define STATUS_REQUIRED_BITS    (UINT8_C(0x80) | UINT8_C(0x20) | UINT8_C(0x10))

static struct bme69x_dev g_bme;
static struct bme69x_conf g_conf;
static struct bme69x_heatr_conf g_heatr_conf;
static bool g_initialized = false;

static void print_ready(void)
{
    printf("READY\n");
    fflush(stdout);
}

static void print_pong(void)
{
    printf("PONG\n");
    fflush(stdout);
}

static void print_bye(void)
{
    printf("BYE\n");
    fflush(stdout);
}

static void print_error(const char *code, int32_t detail)
{
    if (detail == INT32_MIN)
    {
        printf("ERR %s\n", code);
    }
    else
    {
        printf("ERR %s %ld\n", code, (long)detail);
    }

    fflush(stdout);
}

static int8_t initialise_sensor(void)
{
    int8_t rslt;

    rslt = bme69x_interface_init(&g_bme, BME69X_SPI_INTF);
    if (rslt != BME69X_OK)
    {
        return rslt;
    }

    rslt = bme69x_init(&g_bme);
    if (rslt != BME69X_OK)
    {
        return rslt;
    }

    rslt = bme69x_get_conf(&g_conf, &g_bme);
    if (rslt != BME69X_OK)
    {
        return rslt;
    }

    g_conf.filter = BME69X_FILTER_OFF;
    g_conf.odr = BME69X_ODR_NONE;
    g_conf.os_hum = BME69X_OS_16X;
    g_conf.os_pres = BME69X_OS_16X;
    g_conf.os_temp = BME69X_OS_16X;

    rslt = bme69x_set_conf(&g_conf, &g_bme);
    if (rslt != BME69X_OK)
    {
        return rslt;
    }

    g_heatr_conf.enable = BME69X_ENABLE;
    g_heatr_conf.heatr_temp = UINT16_C(320);
    g_heatr_conf.heatr_dur = UINT16_C(140);

    rslt = bme69x_set_heatr_conf(BME69X_FORCED_MODE, &g_heatr_conf, &g_bme);
    if (rslt != BME69X_OK)
    {
        return rslt;
    }

    g_initialized = true;
    return BME69X_OK;
}

static void handle_measure_command(int temp_c, int duration_ms)
{
    struct bme69x_data data;
    uint8_t n_fields = 0;
    int8_t rslt;
    uint32_t wait_us;
    uint32_t timestamp_ms;

    if (!g_initialized)
    {
        print_error("NOT_READY", INT32_MIN);
        return;
    }

    if ((temp_c < 100) || (temp_c > 400))
    {
        print_error("TEMP_RANGE", temp_c);
        return;
    }

    if ((duration_ms < 1) || (duration_ms > 40000))
    {
        print_error("DURATION_RANGE", duration_ms);
        return;
    }

    g_heatr_conf.heatr_temp = (uint16_t)temp_c;
    g_heatr_conf.heatr_dur = (uint16_t)duration_ms;

    rslt = bme69x_set_heatr_conf(BME69X_FORCED_MODE, &g_heatr_conf, &g_bme);
    if (rslt != BME69X_OK)
    {
        print_error("SET_HEATR", rslt);
        return;
    }

    rslt = bme69x_set_op_mode(BME69X_FORCED_MODE, &g_bme);
    if (rslt != BME69X_OK)
    {
        print_error("SET_MODE", rslt);
        return;
    }

    wait_us = bme69x_get_meas_dur(BME69X_FORCED_MODE, &g_conf, &g_bme);
    wait_us += (uint32_t)g_heatr_conf.heatr_dur * UINT32_C(1000);
    g_bme.delay_us(wait_us, g_bme.intf_ptr);

    rslt = bme69x_get_data(BME69X_FORCED_MODE, &data, &n_fields, &g_bme);
    if (rslt != BME69X_OK)
    {
        print_error("GET_DATA", rslt);
        return;
    }

    if (n_fields == 0U)
    {
        print_error("NO_DATA", INT32_MIN);
        return;
    }

    if ((data.status & STATUS_REQUIRED_BITS) != STATUS_REQUIRED_BITS)
    {
        print_error("STATUS", data.status);
        return;
    }

    timestamp_ms = coines_get_millis();
    printf("DATA %lu %.2f %.2f %.2f %.2f 0x%02x\n",
           (unsigned long)timestamp_ms,
           (double)data.temperature,
           (double)data.pressure,
           (double)data.humidity,
           (double)data.gas_resistance,
           data.status);
    fflush(stdout);
}

static void process_command_line(const char *line)
{
    char cmd[16];
    int temp = 0;
    int duration = 0;
    int parsed;

    parsed = sscanf(line, "%15s %d %d", cmd, &temp, &duration);
    if (parsed <= 0)
    {
        return;
    }

    if (strcmp(cmd, "MEASURE") == 0)
    {
        if (parsed != 3)
        {
            print_error("MEASURE_ARGS", INT32_MIN);
            return;
        }

        handle_measure_command(temp, duration);
    }
    else if (strcmp(cmd, "PING") == 0)
    {
        print_pong();
    }
    else if (strcmp(cmd, "EXIT") == 0)
    {
        print_bye();
    }
    else
    {
        print_error("UNKNOWN_CMD", INT32_MIN);
    }
}

int main(void)
{
    char buffer[CMD_BUFFER_SIZE];
    int8_t rslt;

#if defined(_WIN32)
    setvbuf(stdout, NULL, _IONBF, 0);
#endif

    rslt = initialise_sensor();
    if (rslt != BME69X_OK)
    {
        print_error("INIT", rslt);
        bme69x_coines_deinit();
        return EXIT_FAILURE;
    }

    print_ready();

    while (fgets(buffer, sizeof(buffer), stdin) != NULL)
    {
        if (strncmp(buffer, "EXIT", 4) == 0)
        {
            print_bye();
            break;
        }

        process_command_line(buffer);
    }

    bme69x_coines_deinit();
    return EXIT_SUCCESS;
}
