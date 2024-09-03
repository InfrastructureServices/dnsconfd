from gi.repository import GLib 

import dnsconfd.configuration
from dnsconfd.fsm.dnsconfd_context import DnsconfdContext, ContextEvent

def test_creation():
    parser = dnsconfd.configuration.DnsconfdArgumentParser()
    parser.add_arguments()

    help_s = parser.format_help()
    assert(help_s)
    usage_s = parser.format_usage()
    assert(usage_s)
    config = vars(parser.parse_args())
    main_loop = GLib.MainLoop()
    ctx = DnsconfdContext(config, main_loop)
    GLib.idle_add(lambda:
                  ctx.transition_function(ContextEvent("STOP")))

    main_loop.run()
    json = ctx.get_status(True)
    assert(json)
    print(json)


if __name__ == '__main__':
    test_creation()
