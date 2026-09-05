# VexPhoneBridge

VexPhoneBridge is the outbound/inbound messaging boundary for VexNative.

The core runtime must not depend on one carrier, cloud vendor, phone OS, or messaging protocol. Instead, VexNative emits a normalized phone-message request and a transport adapter delivers it.

## Goals

- zero recurring service cost when a free/local transport is available
- allow VexNative to initiate messages instead of waiting for a user prompt
- support inbound replies, delivery state, and media as transports permit
- keep personal phone numbers, tokens, chat history, and credentials out of Git
- keep the known-good AI runtime independent from experimental phone transports

## Initial transports

### TeleLink / Windows Phone Link

`telelink` is the preferred Windows+iPhone adapter when the Windows node has a compatible Phone Link installation and Bluetooth hardware. TeleLink is an external MIT-licensed project and is installed outside this repository. VexPhoneBridge invokes its public CLI rather than vendoring its source.

### Future transports

Additional adapters can implement the same contract without changing VexNative core. Candidate paths include a local/direct iMessage helper, a self-hosted push channel, or another free phone messenger bridge.

## Safety / behavior

The proactive layer above this bridge should enforce quiet hours, cooldowns, per-contact authorization, rate limits, and a user-visible kill switch. The transport layer only delivers approved messages; it does not decide when to interrupt someone.
