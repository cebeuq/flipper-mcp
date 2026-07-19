/*
 * mcp_demo — a minimal Flipper app (FAP) scaffolded, built and deployed over USB
 * by flipper-mcp. Shows a counter (OK) and the last key pressed; Back exits.
 */
#include <furi.h>
#include <gui/gui.h>
#include <gui/view_port.h>
#include <input/input.h>

typedef struct {
    FuriMessageQueue* queue;
    int counter;
    const char* last_key;
} AppState;

/* Draw callback: runs on the GUI thread; reads the shared AppState. */
static void mcp_demo_draw_callback(Canvas* canvas, void* context) {
    AppState* state = context;
    char buf[32];

    canvas_clear(canvas);
    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str(canvas, 2, 12, "flipper-mcp demo");

    canvas_set_font(canvas, FontSecondary);
    snprintf(buf, sizeof(buf), "OK presses: %d", state->counter);
    canvas_draw_str(canvas, 2, 30, buf);
    snprintf(buf, sizeof(buf), "Last key: %s", state->last_key);
    canvas_draw_str(canvas, 2, 44, buf);
    canvas_draw_str(canvas, 2, 60, "Press Back to exit");
}

/* Input callback: runs on the GUI thread; forward events to our queue. */
static void mcp_demo_input_callback(InputEvent* input_event, void* context) {
    FuriMessageQueue* queue = context;
    furi_message_queue_put(queue, input_event, FuriWaitForever);
}

int32_t mcp_demo_app(void* p) {
    UNUSED(p);

    AppState state = {
        .queue = furi_message_queue_alloc(8, sizeof(InputEvent)),
        .counter = 0,
        .last_key = "-",
    };

    ViewPort* view_port = view_port_alloc();
    view_port_draw_callback_set(view_port, mcp_demo_draw_callback, &state);
    view_port_input_callback_set(view_port, mcp_demo_input_callback, state.queue);

    Gui* gui = furi_record_open(RECORD_GUI);
    gui_add_view_port(gui, view_port, GuiLayerFullscreen);

    InputEvent event;
    bool running = true;
    while(running) {
        if(furi_message_queue_get(state.queue, &event, FuriWaitForever) == FuriStatusOk) {
            if(event.type == InputTypeShort) {
                switch(event.key) {
                case InputKeyBack:
                    running = false;
                    break;
                case InputKeyOk:
                    state.counter++;
                    state.last_key = "OK";
                    break;
                case InputKeyUp:
                    state.last_key = "UP";
                    break;
                case InputKeyDown:
                    state.last_key = "DOWN";
                    break;
                case InputKeyLeft:
                    state.last_key = "LEFT";
                    break;
                case InputKeyRight:
                    state.last_key = "RIGHT";
                    break;
                default:
                    break;
                }
            }
            view_port_update(view_port);
        }
    }

    gui_remove_view_port(gui, view_port);
    furi_record_close(RECORD_GUI);
    view_port_free(view_port);
    furi_message_queue_free(state.queue);

    return 0;
}
