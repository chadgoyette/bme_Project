#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void print_usage(void) {
    printf("Usage:\n");
    printf("  bme690_logger --port <port> --sample-rate <hz> --heater-profile <profile> \\\n");
    printf("    --duration-sec <seconds> --warmup-sec <seconds> [--cycles <count>] --out <file>\n");
}

int main(int argc, char **argv) {
    if (argc == 1) {
        print_usage();
        return 1;
    }

    const char *out_path = NULL;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--out") == 0 && i + 1 < argc) {
            out_path = argv[++i];
        }
    }

    if (out_path == NULL) {
        fprintf(stderr, "Missing required --out argument.\n");
        print_usage();
        return 1;
    }

    FILE *fp = fopen(out_path, "w");
    if (!fp) {
        perror("Unable to open output file");
        return 1;
    }

    fprintf(fp, "timestamp_ms,gas_resistance_ohms,temperature_C,humidity_pct,pressure_Pa\n");
    fclose(fp);

    printf("Stub logger wrote CSV header to %s\n", out_path);
    printf("TODO: integrate COINES initialisation, configure heater profile, and stream sensor data.\n");
    return 0;
}
