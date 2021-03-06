import asyncio
import pytest

import zigpy.types
from zigpy.zdo.types import SizePrefixedSimpleDescriptor

import zigpy_znp.types as t
import zigpy_znp.commands as c


from ..conftest import FORMED_DEVICES


pytestmark = [pytest.mark.timeout(1), pytest.mark.asyncio]


@pytest.mark.parametrize("device", FORMED_DEVICES)
async def test_permit_join(device, make_application):
    app, znp_server = make_application(server_cls=device)

    # Handle the ZDO broadcast sent by Zigpy
    data_req_sent = znp_server.reply_once_to(
        request=c.AF.DataRequestExt.Req(partial=True, SrcEndpoint=0, DstEndpoint=0),
        responses=[
            c.AF.DataRequestExt.Rsp(Status=t.Status.SUCCESS),
            c.AF.DataConfirm.Callback(Status=t.Status.SUCCESS, Endpoint=0, TSN=1),
        ],
    )

    # Handle the permit join request sent by us
    permit_join_sent = znp_server.reply_once_to(
        request=c.ZDO.MgmtPermitJoinReq.Req(Duration=10, partial=True),
        responses=[
            c.ZDO.MgmtPermitJoinReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.MgmtPermitJoinRsp.Callback(Src=0xFFFC, Status=t.ZDOStatus.SUCCESS),
        ],
    )

    await app.startup(auto_form=False)
    await app.permit(time_s=10)

    # Make sure both commands were received
    await asyncio.gather(data_req_sent, permit_join_sent)

    await app.shutdown()


@pytest.mark.parametrize("device", FORMED_DEVICES)
async def test_permit_join_failure(device, make_application):
    app, znp_server = make_application(server_cls=device)

    # Handle the ZDO broadcast sent by Zigpy
    data_req_sent = znp_server.reply_once_to(
        request=c.AF.DataRequestExt.Req(partial=True, SrcEndpoint=0, DstEndpoint=0),
        responses=[
            c.AF.DataRequestExt.Rsp(Status=t.Status.SUCCESS),
            c.AF.DataConfirm.Callback(Status=t.Status.SUCCESS, Endpoint=0, TSN=1),
        ],
    )

    # Handle the permit join request sent by us
    permit_join_sent = znp_server.reply_once_to(
        request=c.ZDO.MgmtPermitJoinReq.Req(Duration=10, partial=True),
        responses=[
            c.ZDO.MgmtPermitJoinReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.MgmtPermitJoinRsp.Callback(Src=0xFFFC, Status=t.ZDOStatus.TIMEOUT),
        ],
    )

    await app.startup(auto_form=False)

    with pytest.raises(RuntimeError):
        await app.permit(time_s=10)

    # Make sure both commands were received
    await asyncio.gather(data_req_sent, permit_join_sent)

    await app.shutdown()


@pytest.mark.parametrize("device", FORMED_DEVICES)
async def test_on_zdo_device_join(device, make_application, mocker):
    app, znp_server = make_application(server_cls=device)
    await app.startup(auto_form=False)

    mocker.patch.object(app, "handle_join")

    nwk = 0x1234
    ieee = t.EUI64.convert("11:22:33:44:55:66:77:88")

    znp_server.send(c.ZDO.TCDevInd.Callback(SrcNwk=nwk, SrcIEEE=ieee, ParentNwk=0x0001))
    app.handle_join.assert_called_once_with(nwk=nwk, ieee=ieee, parent_nwk=0x0001)

    await app.shutdown()


@pytest.mark.parametrize("device", FORMED_DEVICES)
async def test_new_device_join_and_bind_complex(device, make_application, mocker):
    app, znp_server = make_application(server_cls=device)
    await app.startup(auto_form=False)

    nwk = 0x6A7C
    ieee = t.EUI64.convert("00:17:88:01:08:64:6C:81")

    # Handle the ZDO permit join broadcast sent by Zigpy
    znp_server.reply_once_to(
        request=c.AF.DataRequestExt.Req(
            partial=True,
            DstAddrModeAddress=t.AddrModeAddress(
                mode=t.AddrMode.Broadcast,
                address=zigpy.types.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
            ),
            DstEndpoint=0,
            DstPanId=0x0000,
            SrcEndpoint=0,
            ClusterId=54,
            Radius=0,
            Data=b"\x01\x3C\x00",
        ),
        responses=[
            c.AF.DataRequestExt.Rsp(Status=t.Status.SUCCESS),
            lambda r: c.AF.DataConfirm.Callback(
                Status=t.Status.SUCCESS, Endpoint=0, TSN=r.TSN
            ),
        ],
    )

    znp_server.reply_once_to(
        request=c.ZDO.MgmtPermitJoinReq.Req(partial=True),
        responses=[
            c.ZDO.MgmtPermitJoinReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.MgmtPermitJoinRsp.Callback(Src=0xFFFC, Status=t.ZDOStatus.SUCCESS),
            c.ZDO.TCDevInd.Callback(SrcNwk=nwk, SrcIEEE=ieee, ParentNwk=0x0000),
        ],
    )

    znp_server.reply_to(
        request=c.ZDO.NodeDescReq.Req(DstAddr=nwk, NWKAddrOfInterest=nwk),
        responses=[
            c.ZDO.NodeDescReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.EndDeviceAnnceInd.Callback(
                Src=nwk,
                NWK=nwk,
                IEEE=ieee,
                Capabilities=c.zdo.MACCapabilities.AllocateShortAddrDuringAssocNeeded,
            ),
            c.ZDO.NodeDescRsp.Callback(
                Src=nwk,
                Status=t.ZDOStatus.SUCCESS,
                NWK=nwk,
                NodeDescriptor=c.zdo.NullableNodeDescriptor(
                    2, 64, 128, 4107, 89, 63, 0, 63, 0
                ),
            ),
        ],
    )

    znp_server.reply_to(
        request=c.ZDO.ActiveEpReq.Req(DstAddr=nwk, NWKAddrOfInterest=nwk),
        responses=[
            c.ZDO.ActiveEpReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.ActiveEpRsp.Callback(
                Src=nwk, Status=t.ZDOStatus.SUCCESS, NWK=nwk, ActiveEndpoints=[2, 1]
            ),
        ],
    )

    znp_server.reply_to(
        request=c.ZDO.SimpleDescReq.Req(DstAddr=nwk, NWKAddrOfInterest=nwk, Endpoint=2),
        responses=[
            c.ZDO.SimpleDescReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.SimpleDescRsp.Callback(
                Src=nwk,
                Status=t.ZDOStatus.SUCCESS,
                NWK=nwk,
                SimpleDescriptor=SizePrefixedSimpleDescriptor(
                    2, 260, 263, 0, [0, 1, 3, 1030, 1024, 1026], [25]
                ),
            ),
        ],
    )

    znp_server.reply_to(
        request=c.ZDO.SimpleDescReq.Req(DstAddr=nwk, NWKAddrOfInterest=nwk, Endpoint=1),
        responses=[
            c.ZDO.SimpleDescReq.Rsp(Status=t.Status.SUCCESS),
            c.ZDO.SimpleDescRsp.Callback(
                Src=nwk,
                Status=t.ZDOStatus.SUCCESS,
                NWK=nwk,
                SimpleDescriptor=SizePrefixedSimpleDescriptor(
                    1, 49246, 2128, 2, [0], [0, 3, 4, 6, 8, 768, 5]
                ),
            ),
        ],
    )

    def data_req_callback(request):
        if request.Data == bytes([0x00, request.TSN]) + b"\x00\x04\x00\x05\x00":
            # Manufacturer + model
            znp_server.send(c.AF.DataRequestExt.Rsp(Status=t.Status.SUCCESS))
            znp_server.send(
                c.AF.DataConfirm.Callback(
                    Status=t.Status.SUCCESS,
                    Endpoint=request.SrcEndpoint,
                    TSN=request.TSN,
                )
            )
            znp_server.send(
                c.AF.IncomingMsg.Callback(
                    GroupId=0x0000,
                    ClusterId=request.ClusterId,
                    SrcAddr=nwk,
                    SrcEndpoint=request.DstEndpoint,
                    DstEndpoint=request.SrcEndpoint,
                    WasBroadcast=t.Bool.false,
                    LQI=156,
                    SecurityUse=t.Bool.false,
                    TimeStamp=2123652,
                    TSN=0,
                    Data=b"\x18"
                    + bytes([request.TSN])
                    + b"\x01\x04\x00\x00\x42\x07\x50\x68\x69\x6C\x69\x70\x73\x05\x00"
                    + b"\x00\x42\x06\x53\x4D\x4C\x30\x30\x31",
                    MacSrcAddr=nwk,
                    MsgResultRadius=29,
                )
            )
        elif request.Data == bytes([0x00, request.TSN]) + b"\x00\x04\x00":
            # Manufacturer
            znp_server.send(c.AF.DataRequestExt.Rsp(Status=t.Status.SUCCESS))
            znp_server.send(
                c.AF.DataConfirm.Callback(
                    Status=t.Status.SUCCESS,
                    Endpoint=request.SrcEndpoint,
                    TSN=request.TSN,
                )
            )
            znp_server.send(
                c.AF.IncomingMsg.Callback(
                    GroupId=0x0000,
                    ClusterId=request.ClusterId,
                    SrcAddr=nwk,
                    SrcEndpoint=request.DstEndpoint,
                    DstEndpoint=request.SrcEndpoint,
                    WasBroadcast=t.Bool.false,
                    LQI=156,
                    SecurityUse=t.Bool.false,
                    TimeStamp=2123652,
                    TSN=0,
                    Data=b"\x18"
                    + bytes([request.TSN])
                    + b"\x01\x04\x00\x00\x42\x07\x50\x68\x69\x6C\x69\x70\x73",
                    MacSrcAddr=nwk,
                    MsgResultRadius=29,
                )
            )
        elif request.Data == bytes([0x00, request.TSN]) + b"\x00\x05\x00":
            # Model
            znp_server.send(c.AF.DataRequestExt.Rsp(Status=t.Status.SUCCESS))
            znp_server.send(
                c.AF.DataConfirm.Callback(
                    Status=t.Status.SUCCESS,
                    Endpoint=request.SrcEndpoint,
                    TSN=request.TSN,
                )
            )
            znp_server.send(
                c.AF.IncomingMsg.Callback(
                    GroupId=0x0000,
                    ClusterId=request.ClusterId,
                    SrcAddr=nwk,
                    SrcEndpoint=request.DstEndpoint,
                    DstEndpoint=request.SrcEndpoint,
                    WasBroadcast=t.Bool.false,
                    LQI=156,
                    SecurityUse=t.Bool.false,
                    TimeStamp=2123652,
                    TSN=0,
                    Data=b"\x18"
                    + bytes([request.TSN])
                    + b"\x01\x05\x00\x00\x42\x06\x53\x4D\x4C\x30\x30\x31",
                    MacSrcAddr=nwk,
                    MsgResultRadius=29,
                )
            )

    znp_server.callback_for_response(
        c.AF.DataRequestExt.Req(
            partial=True,
            DstAddrModeAddress=t.AddrModeAddress(mode=t.AddrMode.NWK, address=nwk),
        ),
        data_req_callback,
    )

    device_future = asyncio.get_running_loop().create_future()

    class TestListener:
        def device_initialized(self, device):
            device_future.set_result(device)

    app.add_listener(TestListener())

    await app.permit(time_s=60)  # duration is sent as byte 0x3C in first ZDO broadcast

    # The device has finally joined and been initialized
    device = await device_future

    assert not device.initializing
    assert device.model == "SML001"
    assert device.manufacturer == "Philips"
    assert set(device.endpoints.keys()) == {0, 1, 2}

    assert set(device.endpoints[1].in_clusters.keys()) == {0}
    assert set(device.endpoints[1].out_clusters.keys()) == {0, 3, 4, 6, 8, 768, 5}

    assert set(device.endpoints[2].in_clusters.keys()) == {0, 1, 3, 1030, 1024, 1026}
    assert set(device.endpoints[2].out_clusters.keys()) == {25}

    # Once we've confirmed the device is good, start testing binds
    def bind_req_callback(request):
        assert request.Dst == nwk
        assert request.Src == ieee
        assert request.SrcEndpoint in device.endpoints

        cluster = request.ClusterId
        ep = device.endpoints[request.SrcEndpoint]
        assert cluster in ep.in_clusters or cluster in ep.out_clusters

        assert request.Address.ieee == app.ieee
        assert request.Address.addrmode == 0x03

        # Make sure the endpoint profiles match up
        our_ep = request.Address.endpoint
        assert app.get_device(nwk=0x0000).endpoints[our_ep].profile_id == ep.profile_id

        znp_server.send(c.ZDO.BindReq.Rsp(Status=t.Status.SUCCESS))
        znp_server.send(c.ZDO.BindRsp.Callback(Src=nwk, Status=t.ZDOStatus.SUCCESS))

    znp_server.callback_for_response(
        c.ZDO.BindReq.Req(Dst=nwk, Src=ieee, partial=True), bind_req_callback
    )

    for ep_id, endpoint in device.endpoints.items():
        if ep_id == 0:
            continue

        for cluster in endpoint.in_clusters.values():
            await cluster.bind()

    await app.shutdown()
