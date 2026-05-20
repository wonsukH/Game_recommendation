
def route_by_mode(state):
    mode = state['parsed_json'].get("mode", "general")
    return f"{mode}_node"
