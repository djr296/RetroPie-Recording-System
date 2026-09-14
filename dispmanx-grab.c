/* Emit the composed Raspberry Pi display as consecutive RGB565 frames. */
#define _POSIX_C_SOURCE 200809L
#include <bcm_host.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile sig_atomic_t keep_running = 1;
static uint8_t y_table[65536];
static uint8_t u_table[65536];
static uint8_t v_table[65536];

static void stop_capture(int signum) {
    (void)signum;
    keep_running = 0;
}

static int positive_number(const char *text, const char *label) {
    char *end = NULL;
    long value = strtol(text, &end, 10);
    if (!text[0] || !end || *end || value < 1 || value > 1000000) {
        fprintf(stderr, "Invalid %s: %s\n", label, text);
        exit(2);
    }
    return (int)value;
}

static void add_ns(struct timespec *value, long ns) {
    value->tv_nsec += ns;
    while (value->tv_nsec >= 1000000000L) {
        value->tv_nsec -= 1000000000L;
        value->tv_sec++;
    }
}

static uint8_t clamp_byte(int value) {
    if (value < 0) return 0;
    if (value > 255) return 255;
    return (uint8_t)value;
}

static void prepare_yuv_tables(void) {
    for (unsigned value = 0; value < 65536; value++) {
        int r = ((value >> 11) & 31) * 255 / 31;
        int g = ((value >> 5) & 63) * 255 / 63;
        int b = (value & 31) * 255 / 31;
        y_table[value] = clamp_byte(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
        u_table[value] = clamp_byte(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
        v_table[value] = clamp_byte(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
    }
}

static void rgb565_to_yuv420(const uint8_t *source, uint32_t source_pitch,
                             uint8_t *dest, uint32_t width, uint32_t height) {
    uint8_t *y_plane = dest;
    uint8_t *u_plane = y_plane + ((size_t)width * height);
    uint8_t *v_plane = u_plane + ((size_t)width * height / 4u);
    for (uint32_t row = 0; row < height; row += 2) {
        const uint16_t *top = (const uint16_t *)(source + ((size_t)row * source_pitch));
        const uint16_t *bottom = (const uint16_t *)(source + ((size_t)(row + 1) * source_pitch));
        uint8_t *y_top = y_plane + ((size_t)row * width);
        uint8_t *y_bottom = y_top + width;
        uint8_t *u_row = u_plane + ((size_t)(row / 2) * (width / 2));
        uint8_t *v_row = v_plane + ((size_t)(row / 2) * (width / 2));
        for (uint32_t column = 0; column < width; column += 2) {
            uint16_t p0 = top[column], p1 = top[column + 1];
            uint16_t p2 = bottom[column], p3 = bottom[column + 1];
            y_top[column] = y_table[p0];
            y_top[column + 1] = y_table[p1];
            y_bottom[column] = y_table[p2];
            y_bottom[column + 1] = y_table[p3];
            u_row[column / 2] = (uint8_t)((u_table[p0] + u_table[p1] +
                                            u_table[p2] + u_table[p3] + 2) / 4);
            v_row[column / 2] = (uint8_t)((v_table[p0] + v_table[p1] +
                                            v_table[p2] + v_table[p3] + 2) / 4);
        }
    }
}

int main(int argc, char **argv) {
    int requested_width = 0, requested_height = 0;
    int fps = 30, frame_limit = 0;
    int output_yuv420 = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--width") && i + 1 < argc)
            requested_width = positive_number(argv[++i], "width");
        else if (!strcmp(argv[i], "--height") && i + 1 < argc)
            requested_height = positive_number(argv[++i], "height");
        else if (!strcmp(argv[i], "--fps") && i + 1 < argc)
            fps = positive_number(argv[++i], "fps");
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc)
            frame_limit = positive_number(argv[++i], "frames");
        else if (!strcmp(argv[i], "--format") && i + 1 < argc) {
            const char *format = argv[++i];
            if (!strcmp(format, "yuv420p")) output_yuv420 = 1;
            else if (!strcmp(format, "rgb565le")) output_yuv420 = 0;
            else {
                fprintf(stderr, "Unsupported format: %s\n", format);
                return 2;
            }
        }
        else {
            fprintf(stderr,
                    "Usage: %s [--width N] [--height N] [--fps N] [--frames N] "
                    "[--format rgb565le|yuv420p]\n",
                    argv[0]);
            return 2;
        }
    }

    signal(SIGINT, stop_capture);
    signal(SIGTERM, stop_capture);
    bcm_host_init();

    DISPMANX_DISPLAY_HANDLE_T display = vc_dispmanx_display_open(0);
    if (display == DISPMANX_NO_HANDLE) {
        fprintf(stderr, "vc_dispmanx_display_open failed\n");
        return 1;
    }
    DISPMANX_MODEINFO_T info;
    if (vc_dispmanx_display_get_info(display, &info) != 0) {
        fprintf(stderr, "vc_dispmanx_display_get_info failed\n");
        vc_dispmanx_display_close(display);
        return 1;
    }

    uint32_t width = requested_width ? (uint32_t)requested_width : (uint32_t)info.width;
    uint32_t height = requested_height ? (uint32_t)requested_height : (uint32_t)info.height;
    uint32_t image_handle = 0;
    DISPMANX_RESOURCE_HANDLE_T resource = vc_dispmanx_resource_create(
        VC_IMAGE_RGB565, width, height, &image_handle);
    if (resource == DISPMANX_NO_HANDLE) {
        fprintf(stderr, "Unable to create %ux%u snapshot resource\n", width, height);
        vc_dispmanx_display_close(display);
        return 1;
    }

    uint32_t pitch = ((width * 2u + 31u) / 32u) * 32u;
    uint8_t *pixels = malloc((size_t)pitch * height);
    size_t yuv_size = (size_t)width * height * 3u / 2u;
    uint8_t *yuv = output_yuv420 ? malloc(yuv_size) : NULL;
    if (!pixels || (output_yuv420 && !yuv)) {
        fprintf(stderr, "Unable to allocate capture buffer\n");
        vc_dispmanx_resource_delete(resource);
        vc_dispmanx_display_close(display);
        return 1;
    }
    VC_RECT_T rectangle;
    vc_dispmanx_rect_set(&rectangle, 0, 0, width, height);
    setvbuf(stdout, NULL, _IOFBF, 1024 * 1024);
    if (output_yuv420 && ((width & 1u) || (height & 1u))) {
        fprintf(stderr, "YUV420 dimensions must be even\n");
        free(yuv);
        free(pixels);
        vc_dispmanx_resource_delete(resource);
        vc_dispmanx_display_close(display);
        return 1;
    }
    if (output_yuv420) prepare_yuv_tables();
    fprintf(stderr, "Display %ux%u, capture %ux%u %s at %d fps\n",
            info.width, info.height, width, height,
            output_yuv420 ? "yuv420p" : "rgb565le", fps);

    struct timespec deadline;
    clock_gettime(CLOCK_MONOTONIC, &deadline);
    long period = 1000000000L / fps;
    int frames = 0;
    while (keep_running && (!frame_limit || frames < frame_limit)) {
        int result = vc_dispmanx_snapshot(display, resource,
                                           (DISPMANX_TRANSFORM_T)0);
        if (result != 0) {
            fprintf(stderr, "Snapshot failed at frame %d: %d\n", frames, result);
            break;
        }
        result = vc_dispmanx_resource_read_data(resource, &rectangle, pixels, pitch);
        if (result != 0) {
            fprintf(stderr, "Read failed at frame %d: %d\n", frames, result);
            break;
        }
        if (output_yuv420) {
            rgb565_to_yuv420(pixels, pitch, yuv, width, height);
            if (fwrite(yuv, 1, yuv_size, stdout) != yuv_size) {
                if (errno != EPIPE)
                    fprintf(stderr, "Output failed: %s\n", strerror(errno));
                keep_running = 0;
            }
        } else {
            for (uint32_t row = 0; row < height; row++) {
                size_t row_bytes = (size_t)width * 2u;
                if (fwrite(pixels + ((size_t)row * pitch), 1, row_bytes, stdout)
                    != row_bytes) {
                    if (errno != EPIPE)
                        fprintf(stderr, "Output failed: %s\n", strerror(errno));
                    keep_running = 0;
                    break;
                }
            }
        }
        frames++;
        add_ns(&deadline, period);
        while (keep_running &&
               clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &deadline, NULL)
                   == EINTR) {
        }
    }

    fflush(stdout);
    fprintf(stderr, "Captured %d frames\n", frames);
    free(yuv);
    free(pixels);
    vc_dispmanx_resource_delete(resource);
    vc_dispmanx_display_close(display);
    return frames ? 0 : 1;
}
