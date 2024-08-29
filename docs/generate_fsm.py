import graphviz

from dnsconfd.fsm.dnsconfd_context import DnsconfdContext

"""
Use this script to generate graph of Dnsconfd FSM
"""
if __name__ == "__main__":
    ctx = DnsconfdContext({"listen_address": "0.0.0.0",
                           "resolv_conf_path": "/", "resolver_options": "edns0", "dnssec_enabled": True, "prioritize_wire": True, "handle_routing": True, "static_servers": {}}, None)

    g = graphviz.Digraph('G', filename='fsm.gv')
    for (key, transitions) in ctx.transition.items():
        for (event, (next_state, cb)) in transitions.items():
            g.edge(key.name, next_state.name, label=event)

    g.render()
