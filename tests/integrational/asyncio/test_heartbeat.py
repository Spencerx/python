import logging
import asyncio
import pytest

import pubnub as pn
from pubnub.pubnub_asyncio import AsyncioSubscriptionManager, PubNubAsyncio, SubscribeListener
from tests import helper
from tests.helper import pnconf_env_copy

pn.set_stream_logger('pubnub', logging.DEBUG)


@pytest.mark.asyncio
async def test_timeout_event_on_broken_heartbeat():
    ch = helper.gen_channel("heartbeat-test")

    messenger_config = pnconf_env_copy(uuid=helper.gen_channel("messenger"), enable_subscribe=True)
    messenger_config.set_presence_timeout(8)
    pubnub = PubNubAsyncio(messenger_config)

    listener_config = pnconf_env_copy(uuid=helper.gen_channel("listener"), enable_subscribe=True)
    pubnub_listener = PubNubAsyncio(listener_config)

    # - connect to :ch-pnpres
    callback_presence = SubscribeListener()
    pubnub_listener.add_listener(callback_presence)
    pubnub_listener.subscribe().channels(ch).with_presence().execute()
    await callback_presence.wait_for_connect()

    envelope = await callback_presence.wait_for_presence_on(ch)
    assert ch == envelope.channel
    assert 'join' == envelope.event
    assert pubnub_listener.uuid == envelope.uuid

    # # - connect to :ch
    callback_messages = SubscribeListener()
    pubnub.add_listener(callback_messages)
    pubnub.subscribe().channels(ch).execute()

    useless_connect_future = asyncio.ensure_future(callback_messages.wait_for_connect())
    presence_future = asyncio.ensure_future(callback_presence.wait_for_presence_on(ch))

    # - assert join event
    await asyncio.wait([useless_connect_future, presence_future])

    prs_envelope = presence_future.result()

    assert ch == prs_envelope.channel
    assert 'join' == prs_envelope.event
    assert pubnub.uuid == prs_envelope.uuid
    # - break messenger heartbeat loop
    pubnub._subscription_manager._stop_heartbeat_timer()

    # wait for one heartbeat call
    await asyncio.sleep(8)

    # - assert for timeout
    envelope = await callback_presence.wait_for_presence_on(ch)
    assert ch == envelope.channel
    assert 'timeout' == envelope.event
    assert pubnub.uuid == envelope.uuid

    pubnub.unsubscribe().channels(ch).execute()
    if isinstance(pubnub._subscription_manager, AsyncioSubscriptionManager):
        await callback_messages.wait_for_disconnect()

    # - disconnect from :ch-pnpres
    pubnub_listener.unsubscribe().channels(ch).execute()
    if isinstance(pubnub._subscription_manager, AsyncioSubscriptionManager):
        await callback_presence.wait_for_disconnect()

    await pubnub.stop()
    await pubnub_listener.stop()
    await asyncio.sleep(0.5)
