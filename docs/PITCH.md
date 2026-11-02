# Wfarhali Agent — pitch

## Short (for the submission form, ~60 words)

Wfarhali Agent is an AI shopping assistant for Algeria. Customers say what they want in Algerian Darija, by voice, text or photo, and the agent finds the product in Wfarhali's live catalogue of international stores, priced in Algerian dinars, within their budget, and sends the confirmed basket to Wfarhali's team. Built on Muse Spark 1.3, Muse Voice Transcribe and SAM 3.1.

## Full pitch (~250 words)

**The problem.** 45 million people speak Algerian Darija, and almost no AI tool understands it. Algerians who want a product from abroad spend hours jumping from site to site, in languages they do not read well, with prices in currencies they cannot pay. Many have no international card. Most shop by sending voice notes.

**What Wfarhali does.** Wfarhali (wfarhali.com) is a live Algerian service: customers order products from international stores, Wfarhali verifies, prices in dinars, pays abroad and delivers. Before the hackathon it had a website and a product search.

**What we built in the hackathon.** An AI agent on top of that service. The customer writes, speaks or sends a photo, in Darija, Arabic, French or English:
- **Muse Spark 1.3** understands the request (products, sizes, colours, a budget said the Algerian way, in centimes), decides what to search and which products are relevant, asks one clear question when something is ambiguous, and talks back in warm Darija.
- **Muse Voice Transcribe** turns Darija voice notes into text.
- **SAM 3.1** locates the exact item in the customer's photo, so the agent can show "this is what I understood" and ask when it sees several items or none.
- The agent searches Wfarhali's live catalogue, and the **basket arithmetic is done by code**, never by the model: exact totals in dinars, within budget, or honestly over it by a stated amount.
- One tap to swap a product; one tap to confirm, which hands the basket to Wfarhali's team on WhatsApp. Human in the loop.

**Why it matters for the business.** One conversation replaces an hour of searching: the customer finds the product they want, in their own words, priced in dinars, with no card and no foreign website. For Wfarhali that means more requests turning into orders, fewer back-and-forth messages for the team, and a channel that finally speaks the customer's language. It costs under one cent per request.

**Next.** Train the agent's Darija on the thousands of real, anonymised search queries customers type on Wfarhali every day.

## البيتش بالعربية (للعرض الشفهي)

**المشكل.** 45 مليون يهدرو الدارجة الجزائرية، وتقريبًا حتى أداة ذكاء اصطناعي ما تفهمها. الجزائري لي يحب منتج من برّا يضيّع ساعات يحوّس من موقع لموقع، بلغات ما يقراهاش مليح، وبأسعار بعملات ما يقدرش يخلّص بيها. وبزاف ما عندهمش بطاقة دولية.

**وفرهالي.** خدمة حقيقية: الزبون يطلب من متاجر عالمية، وفرهالي تتحقق، تسعّر بالدينار، تخلّص برّا وتوصّل. قبل المسابقة كان عندها موقع وبحث.

**واش بنينا في المسابقة.** وكيل ذكاء اصطناعي فوق هذه الخدمة. الزبون يكتب، يهدر ولا يبعث صورة، بالدارجة ولا العربية ولا الفرنسية ولا الإنجليزية. Muse Spark يفهم الطلب (المنتجات، المقاسات، الألوان، والميزانية كيما يقولها الجزائري بالسنتيم)، يختار واش يبحث وأي منتجات مناسبة، يسقسي سؤال واحد كي تكون حاجة غامضة، ويجاوب بالدارجة. Muse Voice Transcribe يحوّل الملاحظة الصوتية لنص. SAM 3.1 يحدّد المنتج بالضبط في الصورة. الوكيل يبحث في كتالوج وفرهالي الحقيقي، وحساب السلة يديرو الكود ماشي الموديل: مجموع دقيق بالدينار، في الميزانية ولا فايتها بمبلغ مذكور بصراحة. ضغطة "بدّل" تبدّل منتج، وضغطة "أكّد" تبعث السلة لفريق وفرهالي على واتساب. الإنسان في الحلقة.

**علاش مهم للبزنس.** محادثة وحدة تعوّض ساعة بحث: الزبون يلقى المنتج لي يحبو، بكلامو هو، بالدينار، بلا بطاقة وبلا مواقع أجنبية. لوفرهالي هذا معناه طلبات أكثر تتحوّل لمبيعات، رسائل أقل على الفريق، وقناة تهدر لغة الزبون أخيرًا. وبأقل من سنت للطلب.

**الخطوة الجاية.** نحسّنو دارجة الوكيل من آلاف كلمات البحث الحقيقية لي يكتبوها الزبائن كل يوم في وفرهالي، بلا أسماء.
